"""Frozen upstream joins, exact label selection and deterministic failed cells."""

# Repository imports this module for semantic validation; keep its import type-only.
from typing import TYPE_CHECKING

from afre.datasets import DatasetManifest
from afre.feature_store.materialization import PointInTimeJoinResult
from afre.feature_store.models import FeatureVintage
from afre.feature_store.providers import MarketBar
from afre.features import DataQuality, MissingState, ValueType
from afre.research_datasets.definitions import ResearchDatasetDefinition
from afre.research_datasets.intervals import SampleInformationInterval
from afre.research_datasets.manifests import (
    DatasetColumn,
    DatasetColumnManifest,
    ResearchDatasetManifest,
    ResearchInputBuild,
)
from afre.research_datasets.samples import ResearchSample, ResearchSelection
from afre.research_datasets.schema import (
    ColumnRole,
    DatasetCompleteness,
    DatasetMissingPolicy,
    PurgeScope,
    SampleState,
)
from afre.schema import require
from afre.target_engine.definitions import TargetDefinition
from afre.target_engine.market_data import TargetBar, TargetSourceBuild
from afre.target_engine.models import TargetDatasetManifest, TargetVintage
from afre.universe.models import UniverseSnapshot
from afre.universe.schema import EligibilityState, SnapshotCompleteness

if TYPE_CHECKING:
    from afre.research_datasets.repository import DatasetRepository


BLOCKED_STATES = (
    SampleState.INELIGIBLE,
    SampleState.UNIVERSE_UNKNOWN,
    SampleState.CONFLICTED,
)


def selection_state(snapshot: UniverseSnapshot, state: EligibilityState) -> SampleState:
    if state is EligibilityState.CONFLICTED:
        return SampleState.CONFLICTED
    if state in (EligibilityState.UNKNOWN, EligibilityState.NOT_AVAILABLE_YET):
        return SampleState.UNIVERSE_UNKNOWN
    if state is not EligibilityState.ELIGIBLE:
        return SampleState.INELIGIBLE
    if snapshot.completeness is not SnapshotCompleteness.COMPLETE:
        return SampleState.UNIVERSE_UNKNOWN
    return SampleState.AVAILABLE


def validate_selection(
    repo: "DatasetRepository",
    selection: ResearchSelection,
    definition: ResearchDatasetDefinition,
) -> None:
    snapshot = repo.resolve(UniverseSnapshot, selection.request.snapshot_id)
    repo.validate_upstream(snapshot)
    compatibility = definition.compatibility
    require(
        snapshot.definition.calendar.fingerprint in compatibility.universe_calendar_ids
        and snapshot.definition.calendar.calendar_id == compatibility.calendar_id,
        "universe calendar outside compatibility contract",
    )
    require(
        snapshot.definition.source.dataset_id in compatibility.source_dataset_ids,
        "universe source outside compatibility contract",
    )
    require(
        snapshot.known_as_of_ns <= snapshot.valid_at_ns,
        "universe future knowledge at research origin",
    )
    require(
        selection.timestamp_ns == snapshot.valid_at_ns
        and selection.cutoff_ns == snapshot.known_as_of_ns,
        "selection/snapshot temporal mismatch",
    )
    eligible = repo.snapshot_eligibility(snapshot).get(selection.security)
    require(
        eligible is not None and eligible.fingerprint == selection.eligibility_id,
        "selection not in exact snapshot security grid",
    )
    assert eligible is not None
    require(
        selection.state == selection_state(snapshot, eligible.state),
        "selection universe state mismatch",
    )
    if selection.state is SampleState.AVAILABLE:
        require(
            selection.origin is not None and selection.join_id is not None,
            "eligible selection requires PIT join",
        )
        assert selection.origin is not None and selection.join_id is not None
        universe = repo.projection(snapshot)
        require(
            selection.origin.universe_id == universe.fingerprint
            and selection.security in repo.snapshot_eligibility(snapshot),
            "selection universe/stable security mismatch",
        )
        join = repo.resolve(PointInTimeJoinResult, selection.join_id)
        require(
            join.row.origin == selection.origin and join.row.dataset.universe == universe,
            "feature join origin/universe mismatch",
        )
        require(
            {x.feature.fingerprint for x in join.audits}
            == {x.fingerprint for x in definition.feature_set.definitions},
            "exact feature set mismatch",
        )
        require(
            all(x.query_policy == definition.query_policy for x in join.audits),
            "feature query policy mismatch",
        )
        validate_join_dataset(join.row.dataset, definition)
        repo._validate_links(join)
    else:
        require(
            selection.origin is None and selection.join_id is None,
            "failed eligibility contains features",
        )
    expected_groups = repo.group_keys(
        definition, selection.security, selection.timestamp_ns, selection.cutoff_ns, eligible
    )
    require(selection.group_keys == expected_groups, "sample group evidence mismatch")
    if selection.request.target_dataset_id is not None:
        labels = repo.resolve(TargetDatasetManifest, selection.request.target_dataset_id)
        repo.validate_upstream(labels)
        require(labels.targets == definition.target_set, "target set mismatch")
        require(
            labels.universe == repo.projection(snapshot),
            "target dataset universe mismatch",
        )
        source = repo.resolve(TargetSourceBuild, labels.source_build_id)
        require(
            source.calendar.fingerprint in compatibility.target_calendar_ids
            and source.calendar.calendar_id == compatibility.calendar_id,
            "target calendar outside compatibility contract",
        )
        require(
            source.source.upstream.dataset_id in compatibility.source_dataset_ids,
            "target source outside compatibility contract",
        )
        if selection.origin is not None:
            require(selection.origin in labels.origins, "missing exact target origin")


def validate_join_dataset(
    dataset: DatasetManifest, definition: ResearchDatasetDefinition
) -> None:
    require(
        dataset.calendar_id == definition.compatibility.calendar_id
        and dataset.adjustment == definition.compatibility.feature_adjustment
        and dataset.source_dataset_ids == definition.compatibility.source_dataset_ids,
        "feature join compatibility mismatch",
    )
    require(
        {x.fingerprint for x in dataset.feature_set.definitions}
        == {x.definition.fingerprint for x in definition.feature_set.definitions},
        "join feature definitions mismatch",
    )


def target_for(
    repo: "DatasetRepository", selection: ResearchSelection, target: TargetDefinition
) -> TargetVintage | None:
    identity = selection.request.target_dataset_id
    if identity is None or selection.origin is None:
        return None
    if identity not in repo._research_rows:
        dataset = repo.resolve(TargetDatasetManifest, identity)
        rows = tuple(repo.resolve(TargetVintage, item) for item in dataset.row_ids)
        mapped = {(row.origin.fingerprint, row.definition.fingerprint): row for row in rows}
        require(len(mapped) == len(rows), "duplicate target origin/definition")
        repo._research_rows[identity] = mapped
    return repo._research_rows[identity].get((selection.origin.fingerprint, target.fingerprint))


def feature_start(repo: "DatasetRepository", vintage: FeatureVintage) -> int:
    identity = vintage.fingerprint
    if identity not in repo._feature_starts:
        starts = [max(0, vintage.effective_ns - vintage.feature.definition.lookback_ns)]
        for ancestor in repo.lineage(identity):
            if isinstance(ancestor, FeatureVintage):
                starts.append(
                    max(0, ancestor.effective_ns - ancestor.feature.definition.lookback_ns)
                )
            elif isinstance(ancestor, MarketBar):
                starts.append(ancestor.period.start_ns)
        repo._feature_starts[identity] = min(starts)
    return repo._feature_starts[identity]


def sample_from(
    repo: "DatasetRepository",
    definition: ResearchDatasetDefinition,
    build: ResearchInputBuild,
    selection: ResearchSelection,
    target: TargetDefinition,
    frozen_join: PointInTimeJoinResult | None = None,
) -> ResearchSample:
    label = target_for(repo, selection, target)
    join = frozen_join or (
        repo.resolve(PointInTimeJoinResult, selection.join_id) if selection.join_id else None
    )
    vintages = (
        tuple(sorted(a.selected.fingerprint for a in join.audits if a.selected)) if join else ()
    )
    interval = None
    if label is not None and label.window is not None:
        start = (
            repo.resolve(TargetBar, label.origin_bar_id).period.end_ns
            if label.origin_bar_id
            else label.window.start_ns
        )
        end = (
            repo.resolve(TargetBar, label.endpoint_bar_id).period.end_ns
            if label.endpoint_bar_id
            else label.window.end_ns
        )
        interval = SampleInformationInterval(start, end, False, True)
    full = interval
    if interval is not None and join is not None:
        earliest = min(
            [
                interval.start_ns,
                *(feature_start(repo, a.selected) for a in join.audits if a.selected),
            ]
        )
        full = SampleInformationInterval(earliest, interval.end_ns, True, True)
    state = selection.state
    if state is SampleState.AVAILABLE:
        if join is None or any(
            a.state is not MissingState.PRESENT
            or a.selected is None
            or a.selected.quality is not DataQuality.VERIFIED
            for a in join.audits
        ):
            state = SampleState.FEATURE_INCOMPLETE
        elif (
            label is None
            or label.clocks.final_available_ns > build.processing_cutoff_ns
            or label.state is MissingState.NOT_AVAILABLE_YET
        ):
            state = SampleState.TARGET_NOT_AVAILABLE_YET
        elif label.state is not MissingState.PRESENT:
            state = SampleState.TARGET_MISSING
        elif label.quality.source_quality is not DataQuality.VERIFIED:
            state = SampleState.INVALID
    dropped = (
        definition.missing_policy is DatasetMissingPolicy.DROP_SAMPLE
        and state is not SampleState.AVAILABLE
    )
    require(
        definition.missing_policy is not DatasetMissingPolicy.FAIL
        or state is SampleState.AVAILABLE,
        "dataset FAIL policy encountered incomplete sample",
    )
    return ResearchSample(
        repo.identity(build),
        repo.identity(selection),
        selection.security,
        selection.origin,
        selection.timestamp_ns,
        selection.request.snapshot_id,
        selection.eligibility_id,
        definition.feature_set.fingerprint,
        selection.join_id,
        vintages,
        target.fingerprint,
        label.fingerprint if label else None,
        interval,
        full,
        label.clocks.final_available_ns if label else None,
        state,
        dropped,
        selection.group_keys,
    )


def columns_for(definition: ResearchDatasetDefinition) -> DatasetColumnManifest:
    return DatasetColumnManifest(
        (
            DatasetColumn("security_id", ColumnRole.IDENTIFIER, ValueType.TEXT, None),
            DatasetColumn("origin_ns", ColumnRole.METADATA, ValueType.INTEGER, None),
            DatasetColumn("sample_state", ColumnRole.METADATA, ValueType.TEXT, None),
            *(
                DatasetColumn("group." + scope.value, ColumnRole.METADATA, ValueType.TEXT, None)
                for scope in (PurgeScope.ISSUER, PurgeScope.SECTOR, PurgeScope.MARKET)
            ),
            *(
                DatasetColumn(
                    x.definition.name,
                    ColumnRole.FEATURE,
                    x.definition.value_type,
                    x.definition.fingerprint,
                )
                for x in definition.feature_set.definitions
            ),
            *(
                DatasetColumn(x.name, ColumnRole.TARGET, ValueType.NUMBER, x.fingerprint)
                for x in definition.target_set.definitions
            ),
        )
    )


def completeness_of(samples: tuple[ResearchSample, ...]) -> DatasetCompleteness:
    if any(s.state is SampleState.UNIVERSE_UNKNOWN for s in samples):
        return DatasetCompleteness.UNKNOWN
    if any(s.state is not SampleState.AVAILABLE for s in samples):
        return DatasetCompleteness.KNOWN_GAPS
    return DatasetCompleteness.COMPLETE


def sample_order(sample: ResearchSample) -> tuple[int, str, str]:
    return (
        sample.timestamp_ns,
        sample.security.instrument.fingerprint,
        sample.target_definition_id,
    )


def dataset_from(
    repo: "DatasetRepository",
    definition: ResearchDatasetDefinition,
    build: ResearchInputBuild,
    samples: tuple[ResearchSample, ...],
) -> ResearchDatasetManifest:
    ordered = tuple(sorted(samples, key=sample_order))
    return ResearchDatasetManifest(
        repo.identity(definition),
        repo.identity(build),
        columns_for(definition),
        tuple(repo.identity(s) for s in ordered),
        completeness_of(samples),
        build.processing_cutoff_ns,
        build.constructed_ns,
    )
