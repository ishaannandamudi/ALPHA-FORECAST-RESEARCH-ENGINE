"""Offline research dataset, split, fold statistics, audit and typed export API."""

import json
from collections.abc import Callable
from time import perf_counter

from afre.datasets import DatasetManifest
from afre.feature_store.engine import FeatureStore
from afre.feature_store.materialization import PointInTimeJoinResult
from afre.features import FeatureSet, MissingPolicy, MissingState
from afre.forecast import ForecastOrigin
from afre.research_datasets.audits import ContaminationAudit, SampleContaminationAudit
from afre.research_datasets.definitions import ResearchDatasetDefinition, ResearchOriginRequest
from afre.research_datasets.fitting import preprocessing_for
from afre.research_datasets.manifests import ResearchDatasetManifest, ResearchInputBuild
from afre.research_datasets.materialization import dataset_from, sample_from, selection_state
from afre.research_datasets.preprocessing import (
    FoldPreprocessingSpec,
    FoldPreprocessingState,
    apply_state,
)
from afre.research_datasets.repository import DatasetRepository
from afre.research_datasets.samples import ResearchSample, ResearchSelection
from afre.research_datasets.schema import (
    BUILDER_VERSION,
    SPLITTER_VERSION,
    Partition,
    SampleState,
)
from afre.research_datasets.splits import (
    FoldDefinition,
    ResearchSplit,
    SplitDefinition,
    TestEvaluation,
)
from afre.research_datasets.splitting import folds_for, memberships_for
from afre.research_datasets.validation import contamination_audit, sample_audit, validate_links
from afre.schema import require
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff
from afre.targets import TargetSpec
from afre.time import TimeRange, validate_timestamp
from afre.universe.models import UniverseSnapshot
from afre.universe.validation import to_universe_manifest


class DatasetEngine:
    def __init__(self, repository: DatasetRepository) -> None:
        self.repository = repository
        self.last_build_timings: dict[str, float] = {}

    def build_dataset(
        self,
        definition: ResearchDatasetDefinition,
        requests: tuple[ResearchOriginRequest, ...],
        processing_cutoff_ns: int,
        constructed_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> ResearchDatasetManifest:
        started = perf_counter()
        pit_seconds = 0.0
        repo = self.repository
        bounds = repo.dataset_bounds
        require(
            definition.implementation_version == BUILDER_VERSION, "unsupported dataset builder"
        )
        require(
            0 < len(requests) <= bounds.origins
            and len({r.snapshot_id for r in requests}) == len(requests),
            "empty/duplicate/oversized origin requests",
        )
        repo._check_bounds(definition)
        selections: list[ResearchSelection] = []
        joins: list[PointInTimeJoinResult] = []
        with repo.read_snapshot(), repo.validation_cache():
            # Establish the SQLite snapshot before the optional concurrency hook.
            repo._connection.execute("SELECT count(*) FROM u_snapshots").fetchone()
            if snapshot_hook is not None:
                snapshot_hook()
            for request in sorted(requests, key=lambda r: r.snapshot_id):
                snapshot = repo.resolve(UniverseSnapshot, request.snapshot_id)
                expected = {e.membership.security: e for e in snapshot.eligibility}
                securities = request.securities or tuple(
                    sorted(expected, key=lambda s: s.fingerprint)
                )
                require(
                    bool(securities) and set(securities) <= set(expected),
                    "requested security outside snapshot evidence grid",
                )
                states = {s: selection_state(snapshot, expected[s].state) for s in securities}
                current_joins: dict[str, PointInTimeJoinResult] = {}
                if SampleState.AVAILABLE in states.values():
                    universe = to_universe_manifest(snapshot)
                    origins = tuple(
                        ForecastOrigin(
                            s.instrument,
                            snapshot.valid_at_ns,
                            snapshot.known_as_of_ns,
                            request.market_session_id,
                            request.build_context,
                            universe.fingerprint,
                        )
                        for s in securities
                        if states[s] is SampleState.AVAILABLE
                    )
                    compatibility = definition.compatibility
                    dataset = DatasetManifest(
                        definition.name,
                        TimeRange(snapshot.valid_at_ns, snapshot.valid_at_ns + 1),
                        universe,
                        FeatureSet(
                            tuple(f.definition for f in definition.feature_set.definitions)
                        ),
                        tuple(
                            TargetSpec(
                                t.target_type,
                                t.horizon,
                                "target-value",
                                t.implementation_version,
                                t.benchmark.instrument if t.benchmark else None,
                            )
                            for t in definition.target_set.definitions
                        ),
                        compatibility.source_dataset_ids,
                        compatibility.calendar_id,
                        compatibility.feature_adjustment,
                        MissingPolicy.EXPLICIT_STATE,
                        BUILDER_VERSION,
                    )
                    # Bound AFRE-1 embedded join output using small batches.
                    with repo._upstream_join_snapshot():
                        for offset in range(0, len(origins), 64):
                            pit_started = perf_counter()
                            results = FeatureStore(
                                repo, definition.query_policy
                            ).point_in_time_join(
                                origins[offset : offset + 64], dataset, definition.feature_set
                            )
                            pit_seconds += perf_counter() - pit_started
                            current_joins.update(
                                (j.row.origin.instrument.fingerprint, j) for j in results
                            )
                    joins.extend(current_joins.values())
                for security in securities:
                    join = current_joins.get(security.instrument.fingerprint)
                    eligible = expected[security]
                    selections.append(
                        ResearchSelection(
                            request,
                            security,
                            snapshot.valid_at_ns,
                            snapshot.known_as_of_ns,
                            join.row.origin if join else None,
                            eligible.fingerprint,
                            join.fingerprint if join else None,
                            states[security],
                            repo.group_keys(
                                definition,
                                security,
                                snapshot.valid_at_ns,
                                snapshot.known_as_of_ns,
                                eligible,
                            ),
                        )
                    )
                    require(
                        len(selections) * len(definition.target_set.definitions)
                        <= bounds.samples,
                        "research sample bound",
                    )
            require(
                len({s.security for s in selections}) <= bounds.securities,
                "research security bound",
            )
            build = ResearchInputBuild(
                definition.fingerprint,
                tuple(s.fingerprint for s in selections),
                processing_cutoff_ns,
                constructed_ns,
            )
            # Later persistence uses exact IDs frozen by this read.
            frozen_joins = {j.fingerprint: j for j in joins}
            samples = tuple(
                sample_from(
                    repo,
                    definition,
                    build,
                    selection,
                    target,
                    frozen_joins.get(selection.join_id or ""),
                )
                for selection in selections
                for target in definition.target_set.definitions
            )
            dataset_manifest = dataset_from(repo, definition, build, samples)
        persistence_started = perf_counter()
        with repo.transaction(), repo.validation_cache():
            repo.put(definition)
            for join in joins:
                repo.put(join)
            for selection in selections:
                repo.put(selection)
            repo.put(build)
            for sample in samples:
                repo.put(sample)
            dataset_id = repo.put(dataset_manifest)
            for sample in samples:
                repo.put(sample_audit(repo, dataset_id, sample.fingerprint))
        persistence_seconds = perf_counter() - persistence_started
        self.last_build_timings = {
            "assembly": persistence_started - started - pit_seconds,
            "pit_joins": pit_seconds,
            "persistence": persistence_seconds,
        }
        return dataset_manifest

    def dataset_samples(self, dataset_id: str) -> tuple[ResearchSample, ...]:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            return self.repository.dataset_samples(dataset_id)

    def build_split(self, dataset_id: str, definition: SplitDefinition) -> ResearchSplit:
        repo = self.repository
        require(
            definition.implementation_version == SPLITTER_VERSION,
            "unsupported split implementation",
        )
        repo._check_bounds(definition)
        with repo.transaction(), repo.validation_cache():
            repo.resolve(ResearchDatasetManifest, dataset_id)
            repo.put(definition)
            folds = folds_for(dataset_id, definition)
            samples = repo.dataset_samples(dataset_id)
            total_comparisons = 0
            for fold in folds:
                repo.put(fold)
                memberships = memberships_for(repo, fold, definition, samples, folds)
                total_comparisons += repo.last_interval_comparisons
                require(
                    total_comparisons <= repo.dataset_bounds.interval_comparisons,
                    "split interval comparison bound",
                )
                for membership in memberships:
                    repo.put(membership)
            split = ResearchSplit(
                dataset_id, definition.fingerprint, tuple(f.fingerprint for f in folds)
            )
            repo.put(split)
        return split

    def folds(self, split_id: str) -> tuple[FoldDefinition, ...]:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            split = self.repository.resolve(ResearchSplit, split_id)
            validate_links(self.repository, split)
            return tuple(self.repository.resolve(FoldDefinition, f) for f in split.fold_ids)

    def partition_samples(
        self, fold_id: str, partition: Partition
    ) -> tuple[ResearchSample, ...]:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            return self.repository.partition_samples(fold_id, partition)

    def training_samples_for_fold(self, fold_id: str) -> tuple[ResearchSample, ...]:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            fold = self.repository.resolve(FoldDefinition, fold_id)
            samples = self.repository.partition_samples(fold_id, Partition.TRAIN)
            require(
                all(
                    s.target_id is not None
                    and target_known_by_cutoff(
                        self.repository.resolve(TargetVintage, s.target_id),
                        fold.training_cutoff_ns,
                    )
                    for s in samples
                ),
                "TRAIN contains unavailable label",
            )
            return samples

    def validation_samples_for_fold(
        self, fold_id: str, evaluation_cutoff_ns: int | None = None
    ) -> tuple[ResearchSample, ...]:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            samples = self.repository.partition_samples(fold_id, Partition.VALIDATION)
            if evaluation_cutoff_ns is None:
                return samples
            validate_timestamp(evaluation_cutoff_ns)
            return tuple(
                s
                for s in samples
                if s.target_id is not None
                and target_known_by_cutoff(
                    self.repository.resolve(TargetVintage, s.target_id), evaluation_cutoff_ns
                )
            )

    def test_samples_for_fold(
        self, fold_id: str, evaluation_id: str, purpose: str, evaluation_cutoff_ns: int
    ) -> tuple[tuple[ResearchSample, ...], TestEvaluation]:
        validate_timestamp(evaluation_cutoff_ns)
        repo = self.repository
        with repo.transaction(), repo.validation_cache():
            samples = repo.partition_samples(fold_id, Partition.TEST)
            ready = tuple(
                s
                for s in samples
                if s.target_id is not None
                and target_known_by_cutoff(
                    repo.resolve(TargetVintage, s.target_id), evaluation_cutoff_ns
                )
            )
            history = tuple(
                repo.resolve(TestEvaluation, row[0])
                for row in repo._connection.execute(
                    "SELECT fingerprint FROM r_artifacts WHERE type_name='TestEvaluation'"
                ).fetchall()
            )
            same = next(
                (
                    e
                    for e in history
                    if e.fold_id == fold_id and e.evaluation_id == evaluation_id
                ),
                None,
            )
            if same is not None:
                require(
                    same.purpose == purpose
                    and same.evaluated_ns == evaluation_cutoff_ns
                    and same.sample_ids == tuple(sorted(s.fingerprint for s in ready)),
                    "conflicting test evaluation identity reuse",
                )
                return ready, same
            evaluation = TestEvaluation(
                fold_id,
                evaluation_id,
                purpose,
                evaluation_cutoff_ns,
                tuple(s.fingerprint for s in ready),
                tuple(e.fingerprint for e in history if e.fold_id == fold_id),
            )
            repo.put(evaluation)
            return ready, evaluation

    def fit_preprocessing(
        self, fold_id: str, spec: FoldPreprocessingSpec, available_ns: int | None = None
    ) -> FoldPreprocessingState:
        repo = self.repository
        with repo.transaction(), repo.validation_cache():
            fold = repo.resolve(FoldDefinition, fold_id)
            state = preprocessing_for(
                repo,
                fold,
                spec,
                fold.training_cutoff_ns if available_ns is None else available_ns,
            )
            repo.put(state.normalization.spec)
            repo.put(state.normalization)
            repo.put(state)
            return state

    def audit_sample(
        self, dataset_id: str, sample_id: str, fold_id: str | None = None
    ) -> SampleContaminationAudit:
        with self.repository.transaction(), self.repository.validation_cache():
            audit = sample_audit(self.repository, dataset_id, sample_id, fold_id)
            self.repository.put(audit)
            return audit

    def audit_dataset(self, dataset_id: str) -> ContaminationAudit:
        with self.repository.transaction(), self.repository.validation_cache():
            audit = contamination_audit(self.repository, dataset_id)
            self.repository.put(audit)
            return audit

    def audit_fold(self, fold_id: str) -> ContaminationAudit:
        with self.repository.transaction(), self.repository.validation_cache():
            fold = self.repository.resolve(FoldDefinition, fold_id)
            audit = contamination_audit(self.repository, fold.dataset_id, fold_id)
            self.repository.put(audit)
            return audit

    def export_rows(
        self,
        dataset_id: str,
        known_as_of_ns: int,
        preprocessing: FoldPreprocessingState | None = None,
        application_ns: int | None = None,
    ) -> str:
        validate_timestamp(known_as_of_ns)
        if application_ns is not None:
            validate_timestamp(application_ns)
        repo = self.repository
        with repo.read_snapshot(), repo.validation_cache():
            dataset = repo.resolve(ResearchDatasetManifest, dataset_id)
            if preprocessing is not None:
                require(
                    preprocessing.dataset_id == dataset_id and application_ns is not None,
                    "export preprocessing requires matching dataset/application time",
                )
                validate_links(repo, preprocessing)
            rows = []
            size = 0
            for sample in repo.dataset_samples(dataset_id):
                join = (
                    repo.resolve(PointInTimeJoinResult, sample.join_id)
                    if sample.join_id
                    else None
                )
                label = (
                    repo.resolve(TargetVintage, sample.target_id) if sample.target_id else None
                )
                truth_ready = label is not None and target_known_by_cutoff(
                    label, known_as_of_ns
                )
                cells: dict[str, object] = {}
                for column in dataset.columns.columns:
                    if column.name == "security_id":
                        value: object = sample.security.instrument.fingerprint
                    elif column.name == "origin_ns":
                        value = sample.timestamp_ns
                    elif column.name == "sample_state":
                        value = sample.state.value
                    elif column.name.startswith("group."):
                        value = dict(sample.group_keys).get(column.name.removeprefix("group."))
                    elif column.role.value == "feature":
                        feature = (
                            next(
                                (
                                    f
                                    for f in join.row.features
                                    if f.definition.fingerprint == column.definition_id
                                ),
                                None,
                            )
                            if join
                            else None
                        )
                        raw = feature.value if feature else None
                        if (
                            preprocessing is not None
                            and column.definition_id
                            == preprocessing.spec.normalization.feature.definition.fingerprint
                        ):
                            assert application_ns is not None
                            require(
                                feature is None or application_ns >= feature.available_ns,
                                "preprocessing applied before input availability",
                            )
                            raw = apply_state(
                                preprocessing,
                                float(raw) if isinstance(raw, (int, float)) else None,
                                application_ns,
                            )
                        value = {
                            "value": raw,
                            "missing_state": feature.missing_state.value
                            if feature
                            else MissingState.NOT_APPLICABLE.value,
                            "quality": feature.quality.value if feature else None,
                            "preprocessing_state_id": preprocessing.fingerprint
                            if preprocessing is not None
                            and column.definition_id
                            == preprocessing.spec.normalization.feature.definition.fingerprint
                            else None,
                        }
                    else:
                        matching = column.definition_id == sample.target_definition_id
                        evidence_known = (
                            label is not None
                            and label.clocks.final_available_ns <= known_as_of_ns
                        )
                        value = {
                            "value": label.value
                            if label is not None and matching and evidence_known
                            else None,
                            "missing_state": label.state.value
                            if label is not None and matching and evidence_known
                            else MissingState.NOT_AVAILABLE_YET.value,
                            "target_known_by_cutoff": matching and truth_ready,
                            "quality": label.quality.source_quality.value
                            if label is not None and matching and evidence_known
                            else None,
                        }

                    cells[column.name] = {
                        "role": column.role.value,
                        "value_type": column.value_type.value,
                        "data": value,
                    }
                row = {
                    "sample_id": repo.identity(sample),
                    "cells": cells,
                    "dropped": sample.dropped,
                }
                size += len(
                    json.dumps(
                        row, sort_keys=True, separators=(",", ":"), allow_nan=False
                    ).encode()
                )
                require(
                    size <= repo.dataset_bounds.serialized_bytes, "export serialized byte bound"
                )
                rows.append(row)
            result = json.dumps(
                {
                    "dataset_id": dataset_id,
                    "known_as_of_ns": known_as_of_ns,
                    "application_ns": application_ns,
                    "rows": rows,
                },
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            require(
                len(result.encode()) <= repo.dataset_bounds.serialized_bytes,
                "export serialized byte bound",
            )
            return result
