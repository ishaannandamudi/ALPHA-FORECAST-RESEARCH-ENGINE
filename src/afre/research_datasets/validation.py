"""Recompute research semantics from frozen evidence, never from a new live as-of join."""

from collections import Counter
from dataclasses import replace
from typing import TYPE_CHECKING

from afre.feature_store.materialization import PointInTimeJoinResult
from afre.feature_store.models import SourceReference
from afre.research_datasets.audits import ContaminationAudit, SampleContaminationAudit
from afre.research_datasets.definitions import ResearchDatasetDefinition, ResearchGroupBinding
from afre.research_datasets.fitting import preprocessing_for
from afre.research_datasets.manifests import ResearchDatasetManifest, ResearchInputBuild
from afre.research_datasets.materialization import dataset_from, sample_from, validate_selection
from afre.research_datasets.preprocessing import FoldPreprocessingSpec, FoldPreprocessingState
from afre.research_datasets.samples import ResearchSample, ResearchSelection
from afre.research_datasets.schema import Partition, SampleState
from afre.research_datasets.splits import (
    FoldDefinition,
    FoldMembership,
    ResearchSplit,
    SplitDefinition,
    TestEvaluation,
)
from afre.research_datasets.splitting import folds_for, memberships_for
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.target_engine.models import TargetDatasetManifest, TargetVintage
from afre.target_engine.validation import target_known_by_cutoff
from afre.universe.models import UniverseSnapshot

if TYPE_CHECKING:
    from afre.research_datasets.repository import DatasetRepository


def validate_split_compatibility(
    repo: "DatasetRepository", dataset: ResearchDatasetManifest, split: SplitDefinition
) -> None:
    definition = repo.resolve(ResearchDatasetDefinition, dataset.definition_id)
    compatibility = definition.compatibility
    if split.embargo.calendar_id is not None:
        require(
            split.embargo.calendar_id in compatibility.universe_calendar_ids,
            "embargo calendar outside dataset compatibility",
        )
    grid = split.embargo.bar_grid
    if grid is not None:
        require(grid.calendar_id == compatibility.calendar_id, "embargo bar calendar mismatch")
        source = repo.resolve(SourceReference, grid.source_id)
        require(
            source.dataset_id in compatibility.source_dataset_ids,
            "embargo source outside dataset compatibility",
        )
        require(
            grid.bar_definition
            in {t.bar_definition for t in definition.target_set.definitions},
            "embargo stream outside dataset compatibility",
        )
    for identity in split.preprocessing_spec_ids:
        spec = repo.resolve(FoldPreprocessingSpec, identity)
        require(
            spec.normalization.feature in definition.feature_set.definitions,
            "preprocessing feature outside exact dataset feature set",
        )
    if split.parent_fold_id is not None:
        parent = repo.resolve(FoldDefinition, split.parent_fold_id)
        require(parent.dataset_id == repo.identity(dataset), "parent fold/dataset mismatch")


def validate_links(repo: "DatasetRepository", value: Artifact) -> None:
    if isinstance(value, ResearchDatasetDefinition):
        repo.resolve(type(value.feature_set), value.feature_set.fingerprint)
        repo.resolve(type(value.target_set), value.target_set.fingerprint)
        for binding in value.group_bindings:
            validate_links(repo, binding)
            source = repo.resolve(SourceReference, binding.source_id)
            require(
                source.dataset_id in value.compatibility.source_dataset_ids,
                "group source outside compatibility contract",
            )
    elif isinstance(value, ResearchGroupBinding):
        binding_source = repo.get_any(value.source_id)
        require(
            isinstance(binding_source, SourceReference),
            "group source must be neutral source evidence",
        )
    elif isinstance(value, ResearchSelection):
        snapshot = repo.resolve(UniverseSnapshot, value.request.snapshot_id)
        require(
            value.security in repo.snapshot_eligibility(snapshot)
            and repo.identity(repo.snapshot_eligibility(snapshot)[value.security])
            == value.eligibility_id,
            "selection eligibility outside snapshot",
        )
        if value.join_id is not None:
            repo.resolve(PointInTimeJoinResult, value.join_id)
    elif isinstance(value, ResearchInputBuild):
        definition = repo.resolve(ResearchDatasetDefinition, value.definition_id)
        selections = tuple(repo.resolve(ResearchSelection, s) for s in value.selection_ids)
        require(
            len({(s.security, s.timestamp_ns) for s in selections}) == len(selections),
            "duplicate research security/origin",
        )
        require(
            len({s.timestamp_ns for s in selections}) <= repo.dataset_bounds.origins
            and len({s.security for s in selections}) <= repo.dataset_bounds.securities,
            "research origin/security bound",
        )
        for selection in selections:
            validate_selection(repo, selection, definition)
            snapshot = repo.resolve(UniverseSnapshot, selection.request.snapshot_id)
            require(
                snapshot.constructed_ns <= value.constructed_ns
                and selection.timestamp_ns <= value.processing_cutoff_ns,
                "research build precedes snapshot/origin",
            )
            if selection.join_id is not None:
                join = repo.resolve(PointInTimeJoinResult, selection.join_id)
                require(
                    all(
                        a.selected is None
                        or a.selected.clocks.afre_computed_ns <= value.constructed_ns
                        for a in join.audits
                    ),
                    "research build precedes feature reconstruction",
                )
            if selection.request.target_dataset_id is not None:
                labels = repo.resolve(
                    TargetDatasetManifest, selection.request.target_dataset_id
                )
                require(
                    labels.constructed_ns <= value.constructed_ns
                    and labels.build_cutoff_ns <= value.processing_cutoff_ns,
                    "research build precedes target dataset",
                )
    elif isinstance(value, ResearchSample):
        build = repo.resolve(ResearchInputBuild, value.input_build_id)
        definition = repo.resolve(ResearchDatasetDefinition, build.definition_id)
        require(
            value.selection_id in repo.member_ids(repo.identity(build), build.selection_ids),
            "sample selection outside frozen build",
        )
        target = next(
            (
                t
                for t in definition.target_set.definitions
                if t.fingerprint == value.target_definition_id
            ),
            None,
        )
        require(target is not None, "sample target outside exact target set")
        assert target is not None
        require(
            sample_from(
                repo,
                definition,
                build,
                repo.resolve(ResearchSelection, value.selection_id),
                target,
            )
            == value,
            "research sample deterministic evidence mismatch",
        )
    elif isinstance(value, ResearchDatasetManifest):
        build = repo.resolve(ResearchInputBuild, value.input_build_id)
        require(build.definition_id == value.definition_id, "dataset definition/build mismatch")
        definition = repo.resolve(ResearchDatasetDefinition, value.definition_id)
        samples = (
            repo.dataset_samples(repo.identity(value))
            if repo._connection.execute(
                "SELECT 1 FROM r_artifacts WHERE fingerprint=?", (repo.identity(value),)
            ).fetchone()
            else tuple(repo.resolve(ResearchSample, s) for s in value.sample_ids)
        )
        require(
            {(s.selection_id, s.target_definition_id) for s in samples}
            == {
                (s, t.fingerprint)
                for s in build.selection_ids
                for t in definition.target_set.definitions
            }
            and len(samples)
            == len(build.selection_ids) * len(definition.target_set.definitions),
            "incomplete research sample grid",
        )
        require(
            replace(
                dataset_from(repo, definition, build, samples),
                engine_version=value.engine_version,
            )
            == value,
            "research dataset deterministic manifest mismatch",
        )
    elif isinstance(value, SplitDefinition):
        for identity in value.preprocessing_spec_ids:
            repo.resolve(FoldPreprocessingSpec, identity)
        if value.parent_fold_id is not None:
            repo.resolve(FoldDefinition, value.parent_fold_id)
    elif isinstance(value, FoldDefinition):
        dataset = repo.resolve(ResearchDatasetManifest, value.dataset_id)
        split_definition = repo.resolve(SplitDefinition, value.split_definition_id)
        validate_split_compatibility(repo, dataset, split_definition)
        require(
            value in folds_for(value.dataset_id, split_definition), "fold schedule mismatch"
        )
        require(
            value.training_cutoff_ns <= dataset.processing_cutoff_ns,
            "training cutoff exceeds frozen dataset cutoff",
        )
    elif isinstance(value, FoldMembership):
        fold = repo.resolve(FoldDefinition, value.fold_id)
        sample = repo.resolve(ResearchSample, value.sample_id)
        dataset = repo.resolve(ResearchDatasetManifest, fold.dataset_id)
        require(
            sample.input_build_id == dataset.input_build_id
            and value.sample_id in repo.member_ids(repo.identity(dataset), dataset.sample_ids),
            "fold sample outside dataset",
        )
    elif isinstance(value, ResearchSplit):
        split_definition = repo.resolve(SplitDefinition, value.definition_id)
        folds = folds_for(value.dataset_id, split_definition)
        require(
            value.fold_ids == tuple(f.fingerprint for f in folds),
            "split fold ordering mismatch",
        )
        samples = repo.dataset_samples(value.dataset_id)
        total_comparisons = 0
        for fold in folds:
            repo.resolve(FoldDefinition, fold.fingerprint)
            expected = memberships_for(repo, fold, split_definition, samples, folds)
            total_comparisons += repo.last_interval_comparisons
            require(
                total_comparisons <= repo.dataset_bounds.interval_comparisons,
                "split interval comparison bound",
            )
            actual = repo.fold_memberships(fold.fingerprint)
            require(set(expected) == set(actual), "fold partition/purge/embargo contamination")
    elif isinstance(value, FoldPreprocessingSpec):
        repo.resolve(type(value.normalization.feature), value.normalization.feature.fingerprint)
    elif isinstance(value, FoldPreprocessingState):
        fold = repo.resolve(FoldDefinition, value.fold_id)
        require(
            value.spec.fingerprint
            in repo.resolve(SplitDefinition, fold.split_definition_id).preprocessing_spec_ids,
            "preprocessing spec outside split",
        )
        require(
            value
            == preprocessing_for(repo, fold, value.spec, value.normalization.available_ns),
            "preprocessing TRAIN statistics contamination",
        )
        repo.resolve(type(value.normalization), value.normalization.fingerprint)
    elif isinstance(value, TestEvaluation):
        samples = repo.partition_samples(value.fold_id, Partition.TEST)
        expected_test_ids = tuple(
            sorted(
                repo.identity(s)
                for s in samples
                if s.target_id is not None
                and target_known_by_cutoff(
                    repo.resolve(TargetVintage, s.target_id), value.evaluated_ns
                )
            )
        )
        require(value.sample_ids == expected_test_ids, "test evaluation truth cutoff mismatch")
        for identity in value.previous_evaluation_ids:
            previous = repo.resolve(TestEvaluation, identity)
            require(previous.fold_id == value.fold_id, "test reuse references another fold")
    elif isinstance(value, SampleContaminationAudit):
        require(
            value == sample_audit(repo, value.dataset_id, value.sample_id, value.fold_id),
            "sample contamination audit evidence mismatch",
        )
    elif isinstance(value, ContaminationAudit):
        require(
            value
            == contamination_audit(
                repo, value.dataset_id, value.fold_id, value.preprocessing_state_ids
            ),
            "contamination audit evidence mismatch",
        )


def audit_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, ResearchDatasetManifest):
        return (value.input_build_id, *value.sample_ids)
    if isinstance(value, ResearchInputBuild):
        return (value.definition_id, *value.selection_ids)
    if isinstance(value, ResearchDatasetDefinition):
        return (
            value.feature_set.fingerprint,
            value.target_set.fingerprint,
            *(b.source_id for b in value.group_bindings),
        )
    if isinstance(value, ResearchSelection):
        return (
            value.request.snapshot_id,
            value.eligibility_id,
            *((value.join_id,) if value.join_id else ()),
            *((value.request.target_dataset_id,) if value.request.target_dataset_id else ()),
        )
    if isinstance(value, ResearchSample):
        return (
            value.selection_id,
            *value.feature_vintage_ids,
            *((value.target_id,) if value.target_id else ()),
        )
    if isinstance(value, PointInTimeJoinResult):
        return tuple(a.selected.fingerprint for a in value.audits if a.selected) + tuple(
            a.scope_binding_id for a in value.audits if a.scope_binding_id
        )
    if isinstance(value, FoldPreprocessingState):
        return (value.normalization.fingerprint, *value.fit_sample_ids)
    return ()


def lineage_ids(repo: "DatasetRepository", roots: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    active: set[str] = set()
    size = 0

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "research lineage cycle")
        if identity in seen:
            return
        require(
            depth <= repo.dataset_bounds.lineage_depth
            and len(seen) + len(active) < repo.dataset_bounds.audit_nodes,
            "research lineage depth/node bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        edges = audit_edges(value)
        if edges or identity.startswith("afre.r_") or isinstance(value, PointInTimeJoinResult):
            values: tuple[Artifact, ...] = (value,)
            for edge in sorted(set(edges)):
                visit(edge, depth + 1)
        else:
            values = repo.lineage(identity)
        for item in values:
            key = repo.identity(item)
            if key not in seen:
                seen.add(key)
                size += len(canonical_json(item).encode())
        active.remove(identity)
        require(
            len(seen) <= repo.dataset_bounds.audit_nodes
            and size <= repo.dataset_bounds.serialized_bytes,
            "research lineage node/byte bound",
        )

    for root in roots:
        visit(root, 0)
    return tuple(sorted(seen))


def sample_audit(
    repo: "DatasetRepository", dataset_id: str, sample_id: str, fold_id: str | None = None
) -> SampleContaminationAudit:
    dataset = repo.resolve(ResearchDatasetManifest, dataset_id)
    require(
        sample_id in repo.member_ids(dataset_id, dataset.sample_ids),
        "sample audit outside dataset",
    )
    sample = repo.resolve(ResearchSample, sample_id)
    build = repo.resolve(ResearchInputBuild, dataset.input_build_id)
    repo.validate_upstream(build)
    repo.validate_upstream(sample)
    evidence = (
        sample.input_build_id,
        sample.selection_id,
        sample.snapshot_id,
        sample.eligibility_id,
        sample.feature_set_id,
        sample.target_definition_id,
        *sample.feature_vintage_ids,
        *((sample.join_id,) if sample.join_id else ()),
        *((sample.target_id,) if sample.target_id else ()),
    )
    checks: tuple[str, ...] = (
        "exact-grid-cell",
        "stable-security",
        "explicit-state",
        "pinned-evidence",
        "source-compatibility",
        "target-interval",
    )
    if sample.join_id is not None:
        repo.validate_upstream(repo.resolve(PointInTimeJoinResult, sample.join_id))
        checks += (
            "feature-cutoff",
            "target-excluded-from-feature-lineage",
            "point-in-time-eligibility",
        )
    if sample.target_id is not None:
        repo.validate_upstream(repo.resolve(TargetVintage, sample.target_id))
    partition = None
    if fold_id is not None:
        fold = repo.resolve(FoldDefinition, fold_id)
        require(fold.dataset_id == dataset_id, "sample audit fold/dataset mismatch")
        repo.partition_samples(fold_id, Partition.TRAIN)
        membership = next(m for m in repo.fold_memberships(fold_id) if m.sample_id == sample_id)
        partition = membership.partition
        evidence += (membership.fingerprint,)
        checks += ("partition-boundary", "purge", "embargo")
        if partition is Partition.TRAIN:
            require(
                sample.target_id is not None
                and target_known_by_cutoff(
                    repo.resolve(TargetVintage, sample.target_id), fold.training_cutoff_ns
                ),
                "sample TRAIN target unavailable",
            )
            checks += ("target-known-by-cutoff",)
    require(len(set(evidence)) <= repo.dataset_bounds.audit_nodes, "sample audit node bound")
    return SampleContaminationAudit(
        dataset_id,
        sample_id,
        fold_id,
        sample.state,
        partition,
        tuple(sorted(set(evidence))),
        checks,
    )


def contamination_audit(
    repo: "DatasetRepository",
    dataset_id: str,
    fold_id: str | None = None,
    preprocessing_state_ids: tuple[str, ...] | None = None,
) -> ContaminationAudit:
    dataset = repo.resolve(ResearchDatasetManifest, dataset_id)
    validate_links(repo, repo.resolve(ResearchInputBuild, dataset.input_build_id))
    validate_links(repo, dataset)
    samples = repo.dataset_samples(dataset_id)
    for sample in samples:
        validate_links(repo, sample)
        if sample.target_id is not None:
            repo.validate_upstream(repo.resolve(TargetVintage, sample.target_id))
    partitions: Counter[Partition] = Counter()
    exclusions = tuple(
        repo.identity(s) for s in samples if s.state is not SampleState.AVAILABLE or s.dropped
    )
    checks: tuple[str, ...] = (
        "exact-grid",
        "stable-security",
        "causal-features",
        "point-in-time-universe",
        "pinned-target-evidence",
        "compatibility",
        "missing-trace",
    )
    roots = [dataset_id]
    selected_states: tuple[str, ...] = ()
    if fold_id is not None:
        fold = repo.resolve(FoldDefinition, fold_id)
        require(fold.dataset_id == dataset_id, "audit fold/dataset mismatch")
        validate_links(repo, fold)
        definition = repo.resolve(SplitDefinition, fold.split_definition_id)
        expected = memberships_for(
            repo, fold, definition, samples, folds_for(dataset_id, definition)
        )
        require(set(expected) == set(repo.fold_memberships(fold_id)), "fold contamination")
        partitions.update(m.partition for m in expected)
        exclusions += tuple(
            m.fingerprint
            for m in expected
            if m.partition in (Partition.PURGED, Partition.EMBARGOED, Partition.INELIGIBLE)
        )
        rows = repo._connection.execute(
            "SELECT fingerprint FROM r_artifacts WHERE type_name='FoldPreprocessingState'"
        ).fetchall()
        selected_states = (
            preprocessing_state_ids
            if preprocessing_state_ids is not None
            else tuple(
                row[0]
                for row in rows
                if repo.resolve(FoldPreprocessingState, row[0]).fold_id == fold_id
            )
        )
        for identity in selected_states:
            state = repo.resolve(FoldPreprocessingState, identity)
            require(state.fold_id == fold_id, "audit preprocessing references another fold")
            validate_links(repo, state)
            roots.append(identity)
        checks += (
            "disjoint-partitions",
            "purge",
            "embargo",
            "target-known-by-cutoff",
            "train-only-preprocessing",
            "sealed-test",
        )
    return ContaminationAudit(
        dataset_id,
        fold_id,
        tuple(Counter(s.state for s in samples).items()),
        tuple(partitions.items()),
        exclusions,
        lineage_ids(repo, tuple(roots)),
        checks,
        selected_states,
    )
