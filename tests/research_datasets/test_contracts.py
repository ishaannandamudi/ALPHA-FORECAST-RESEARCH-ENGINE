"""Closed schema, unsupported operations, compatibility and explicit resource bounds."""

from dataclasses import replace

import pytest

from afre.features import DataQuality, MissingState, ValueType
from afre.research_datasets import (
    ColumnRole,
    DatasetBounds,
    DatasetColumn,
    DatasetColumnManifest,
    DatasetMissingPolicy,
    EmbargoBarGrid,
    EmbargoBasis,
    EmbargoDirection,
    EmbargoPolicy,
    Partition,
    PurgePolicy,
    PurgeRule,
    PurgeScope,
    ResearchGroupBinding,
    ResearchInputBuild,
    ResearchSelection,
    SampleInformationInterval,
    SampleState,
    SplitStrategy,
)
from afre.research_datasets.materialization import sample_from, selection_state
from afre.research_datasets.splitting import embargo_intervals, folds_for
from afre.schema import ContractError
from afre.target_engine.models import TargetVintage
from afre.time import TimeRange
from afre.universe.models import UniverseSnapshot
from afre.universe.schema import EligibilityState, SnapshotCompleteness
from examples.feature_store_demo import CALENDAR, INPUT_ID, SOURCE
from examples.research_dataset_demo import split_definition
from tests.research_datasets.conftest import Case


@pytest.mark.parametrize(
    "name",
    [
        "origins",
        "securities",
        "samples",
        "features",
        "targets",
        "folds",
        "interval_comparisons",
        "audit_nodes",
        "lineage_depth",
        "serialized_bytes",
    ],
)
def test_positive_bounds(name: str) -> None:
    with pytest.raises(ContractError, match="positive"):
        replace(DatasetBounds(), **{name: 0})


@pytest.mark.parametrize("invalid_kind", ["namespace", "imputation"])
def test_definition_rejects_unqualified_contract(case: Case, invalid_kind: str) -> None:
    with pytest.raises(ContractError):
        if invalid_kind == "namespace":
            replace(case.fixture.definition, name="unqualified")
        else:
            replace(
                case.fixture.definition, missing_policy=DatasetMissingPolicy.IMPUTE_TRAIN_ONLY
            )


def test_target_cannot_be_a_feature_column(case: Case) -> None:
    target = case.fixture.definition.target_set.definitions[0]
    with pytest.raises(ContractError, match="namespace|fingerprint|identity"):
        DatasetColumn(
            "market.accidental_label", ColumnRole.FEATURE, ValueType.NUMBER, target.fingerprint
        )
    with pytest.raises(ContractError, match="target cannot"):
        DatasetColumn(
            "target.accidental",
            ColumnRole.FEATURE,
            ValueType.NUMBER,
            case.fixture.preprocessing.normalization.feature.definition.fingerprint,
        )
    with pytest.raises(ContractError, match="requires definition"):
        DatasetColumn("market.absent", ColumnRole.FEATURE, ValueType.NUMBER, None)
    with pytest.raises(ContractError, match="requires definition"):
        DatasetColumn("target.absent", ColumnRole.TARGET, ValueType.NUMBER, None)
    with pytest.raises(ContractError, match="empty"):
        DatasetColumnManifest(())


@pytest.mark.parametrize(
    "name", ["calendar", "adjustment", "source", "target_adjustment", "target_calendar"]
)
def test_definition_compatibility(case: Case, name: str) -> None:
    definition = case.fixture.definition
    feature = definition.feature_set.definitions[0]
    if name == "calendar":
        changed = replace(definition.compatibility, calendar_id="different-calendar")
    elif name == "adjustment":
        changed = replace(
            definition.compatibility,
            feature_adjustment=replace(feature.adjustment, known_as_of_ns=1),
        )
    elif name == "source":
        changed = replace(definition.compatibility, source_dataset_ids=(SOURCE.fingerprint,))
    elif name == "target_adjustment":
        changed = replace(
            definition.compatibility,
            target_adjustment_ids=(replace(feature.adjustment, known_as_of_ns=1).fingerprint,),
        )
    else:
        changed = replace(
            definition.compatibility,
            target_calendar_ids=(definition.compatibility.target_calendar_ids[0],),
            universe_calendar_ids=(definition.compatibility.universe_calendar_ids[0],),
        )
        changed_target = replace(
            definition.target_set.definitions[0], calendar_id="different-calendar"
        )
        with pytest.raises(ContractError, match="calendar"):
            replace(
                definition,
                target_set=replace(definition.target_set, definitions=(changed_target,)),
            )
        return
    with pytest.raises(ContractError, match="calendar|adjustment|source"):
        replace(definition, compatibility=changed)


@pytest.mark.parametrize(
    "kind",
    [
        "empty",
        "duplicate",
        "foreign_security",
        "physical_time",
        "sample_bound",
        "security_bound",
        "origin_bound",
        "feature_bound",
        "target_bound",
        "bytes",
    ],
)
def test_build_fails_explicitly(case: Case, kind: str) -> None:
    requests = case.fixture.requests
    definition = case.fixture.definition
    if kind == "empty":
        requests = ()
    elif kind == "duplicate":
        requests = (requests[0], requests[0])
    elif kind == "foreign_security":
        from afre.universe.identity import StableSecurityId

        requests = (replace(requests[0], securities=(StableSecurityId("unknown", "absent"),)),)
    elif kind in (
        "sample_bound",
        "security_bound",
        "origin_bound",
        "feature_bound",
        "target_bound",
        "bytes",
    ):
        field = {
            "sample_bound": "samples",
            "security_bound": "securities",
            "origin_bound": "origins",
            "feature_bound": "features",
            "target_bound": "targets",
            "bytes": "serialized_bytes",
        }[kind]
        if kind == "feature_bound":
            case.repository.dataset_bounds = replace(case.repository.dataset_bounds, features=1)
            from examples.feature_store_demo import definition as feature_definition

            definition = replace(
                definition,
                feature_set=replace(
                    definition.feature_set,
                    definitions=(
                        *definition.feature_set.definitions,
                        feature_definition("market.extra"),
                    ),
                ),
            )
        else:
            case.repository.dataset_bounds = replace(
                case.repository.dataset_bounds, **{field: 1}
            )
    with pytest.raises(ContractError):
        case.engine.build_dataset(
            definition, requests, 100, 90 if kind == "physical_time" else 100
        )


@pytest.mark.parametrize(
    "kind",
    [
        "count",
        "step",
        "fixed",
        "test_overlap",
        "cutoff",
        "fold_bound",
        "comparisons",
        "future_grid",
        "grid_coverage",
    ],
)
def test_split_rejects_invalid_boundary(case: Case, kind: str) -> None:
    definition = split_definition(case.fixture)
    with pytest.raises(ContractError):
        if kind == "count":
            definition = replace(definition, fold_count=0)
        elif kind == "step":
            definition = replace(definition, step_ns=0)
        elif kind == "fixed":
            definition = replace(definition, strategy=SplitStrategy.FIXED_HOLDOUT)
        elif kind == "test_overlap":
            definition = replace(definition, test=TimeRange(50, 60))
        elif kind == "cutoff":
            definition = replace(definition, training_cutoff_ns=41)
        elif kind == "fold_bound":
            case.repository.dataset_bounds = replace(case.repository.dataset_bounds, folds=1)
        elif kind == "comparisons":
            case.repository.dataset_bounds = replace(
                case.repository.dataset_bounds, interval_comparisons=1
            )
        else:
            grid = EmbargoBarGrid(
                CALENDAR,
                "one-unit-bars-v1",
                "1",
                SOURCE.fingerprint,
                41 if kind == "future_grid" else 0,
                (TimeRange(20, 30),),
            )
            definition = replace(
                definition,
                embargo=EmbargoPolicy(
                    EmbargoBasis.BARS, 1, EmbargoDirection.BOTH, bar_grid=grid
                ),
            )
        case.engine.build_split(case.dataset.fingerprint, definition)


@pytest.mark.parametrize("state", list(EligibilityState))
def test_universe_state_mapping(case: Case, state: EligibilityState) -> None:
    snapshot = case.repository.get(UniverseSnapshot, case.fixture.requests[0].snapshot_id)
    mapped = selection_state(snapshot, state)
    if state is EligibilityState.ELIGIBLE:
        assert mapped is SampleState.AVAILABLE
        assert (
            selection_state(
                replace(snapshot, completeness=SnapshotCompleteness.KNOWN_GAPS), state
            )
            is SampleState.UNIVERSE_UNKNOWN
        )
    elif state is EligibilityState.CONFLICTED:
        assert mapped is SampleState.CONFLICTED
    elif state in (EligibilityState.UNKNOWN, EligibilityState.NOT_AVAILABLE_YET):
        assert mapped is SampleState.UNIVERSE_UNKNOWN
    else:
        assert mapped is SampleState.INELIGIBLE


@pytest.mark.parametrize(
    "state,quality,expected",
    [
        (MissingState.MISSING, DataQuality.VERIFIED, SampleState.TARGET_MISSING),
        (
            MissingState.NOT_AVAILABLE_YET,
            DataQuality.VERIFIED,
            SampleState.TARGET_NOT_AVAILABLE_YET,
        ),
        (MissingState.PRESENT, DataQuality.UNVERIFIED, SampleState.INVALID),
    ],
)
def test_target_state_mapping(
    case: Case,
    monkeypatch: pytest.MonkeyPatch,
    state: MissingState,
    quality: DataQuality,
    expected: SampleState,
) -> None:
    sample = next(
        s
        for s in case.engine.dataset_samples(case.dataset.fingerprint)
        if s.state is SampleState.AVAILABLE
    )
    with case.repository.read_snapshot(), case.repository.validation_cache():
        assert sample.target_id is not None
        label = case.repository.resolve(TargetVintage, sample.target_id)
        altered = replace(
            label,
            state=state,
            value=label.value if state is MissingState.PRESENT else None,
            quality=replace(label.quality, source_quality=quality),
        )
        monkeypatch.setattr(
            "afre.research_datasets.materialization.target_for", lambda *args: altered
        )
        selection = case.repository.resolve(ResearchSelection, sample.selection_id)
        build = case.repository.resolve(ResearchInputBuild, sample.input_build_id)
        result = sample_from(
            case.repository, case.fixture.definition, build, selection, label.definition
        )
        assert result.state is expected
        future_build = replace(build, processing_cutoff_ns=1)
        assert (
            sample_from(
                case.repository,
                case.fixture.definition,
                future_build,
                selection,
                label.definition,
            ).state
            is SampleState.TARGET_NOT_AVAILABLE_YET
        )


def test_typed_group_bindings_and_source_contract(case: Case) -> None:
    securities = {s.security for s in case.engine.dataset_samples(case.dataset.fingerprint)}
    groups = tuple(
        ResearchGroupBinding(
            s, PurgeScope.SECTOR, "synthetic-sector", TimeRange(0, 100), 0, SOURCE.fingerprint
        )
        for s in securities
    )
    definition = replace(case.fixture.definition, group_bindings=groups)
    dataset = case.engine.build_dataset(definition, case.fixture.requests, 100, 100)
    split = case.engine.build_split(
        dataset.fingerprint,
        replace(
            split_definition(case.fixture),
            purge=PurgePolicy(PurgeRule.TARGET_INTERVAL_OVERLAP, PurgeScope.SECTOR),
        ),
    )
    assert case.engine.partition_samples(split.fold_ids[0], Partition.PURGED)
    with pytest.raises(ContractError, match="scope"):
        replace(groups[0], scope=PurgeScope.SECURITY)
    with case.repository.transaction(), pytest.raises(ContractError, match="neutral"):
        case.repository.put(replace(groups[0], source_id=case.dataset.fingerprint))
    with pytest.raises(ContractError, match="conflicting"):
        conflicting = replace(
            definition, group_bindings=(*groups, replace(groups[0], group="another-sector"))
        )
        case.engine.build_dataset(conflicting, case.fixture.requests, 100, 100)
    assert INPUT_ID in definition.compatibility.source_dataset_ids


def test_audit_export_and_lineage_bounds(case: Case) -> None:
    case.repository.dataset_bounds = replace(case.repository.dataset_bounds, audit_nodes=1)
    with pytest.raises(ContractError, match="bound"):
        case.engine.audit_dataset(case.dataset.fingerprint)
    case.repository.dataset_bounds = replace(
        case.repository.dataset_bounds, audit_nodes=100000, serialized_bytes=20000
    )
    with pytest.raises(ContractError, match="byte bound"):
        case.engine.export_rows(case.dataset.fingerprint, 100)
    case.repository.dataset_bounds = replace(case.repository.dataset_bounds, lineage_depth=1)
    with pytest.raises(ContractError, match="depth"):
        case.engine.audit_dataset(case.dataset.fingerprint)


def test_invalid_embargo_evidence(case: Case) -> None:
    with pytest.raises(ContractError, match="calendar"):
        EmbargoPolicy(EmbargoBasis.TRADING_SESSIONS)
    with pytest.raises(ContractError, match="grid"):
        EmbargoPolicy(EmbargoBasis.BARS)
    with pytest.raises(ContractError, match="overlap"):
        EmbargoBarGrid(
            CALENDAR, "bars", "1", SOURCE.fingerprint, 0, (TimeRange(10, 20), TimeRange(15, 25))
        )
    definition = replace(
        split_definition(case.fixture),
        embargo=EmbargoPolicy(
            EmbargoBasis.TRADING_SESSIONS,
            9,
            EmbargoDirection.BEFORE,
            case.fixture.definition.compatibility.universe_calendar_ids[0],
        ),
    )
    with (
        case.repository.read_snapshot(),
        case.repository.validation_cache(),
        pytest.raises(ContractError, match="coverage"),
    ):
        embargo_intervals(
            case.repository, definition, folds_for(case.dataset.fingerprint, definition)
        )
    assert SampleInformationInterval(1, 2).start_ns == 1


@pytest.mark.parametrize("cutoff", [-1, True, 2**63])
def test_export_and_evaluation_require_valid_utc_cutoffs(case: Case, cutoff: int) -> None:
    with pytest.raises(ContractError):
        case.engine.export_rows(case.dataset.fingerprint, cutoff)


@pytest.mark.parametrize("mismatch", ["source", "stream", "calendar"])
def test_embargo_requires_exact_dataset_compatibility(case: Case, mismatch: str) -> None:
    source = SOURCE
    if mismatch == "source":
        source = replace(SOURCE, dataset_id=SOURCE.fingerprint)
        with case.repository.transaction():
            case.repository.put(source)
    grid = EmbargoBarGrid(
        "different-calendar" if mismatch == "calendar" else CALENDAR,
        "different-stream" if mismatch == "stream" else "one-unit-bars-v1",
        "1",
        source.fingerprint,
        0,
        (TimeRange(20, 30), TimeRange(40, 50), TimeRange(60, 65)),
    )
    definition = replace(
        split_definition(case.fixture),
        test=None,
        fold_count=1,
        embargo=EmbargoPolicy(EmbargoBasis.BARS, 1, EmbargoDirection.BOTH, bar_grid=grid),
    )
    with pytest.raises(ContractError, match="compatibility|calendar mismatch"):
        case.engine.build_split(case.dataset.fingerprint, definition)


def test_nested_boundary_and_preprocessing_reject_foreign_dataset(case: Case) -> None:
    definition = split_definition(case.fixture)
    parent = case.engine.build_split(case.dataset.fingerprint, definition)
    other = case.engine.build_dataset(case.fixture.definition, case.fixture.requests, 100, 101)
    with pytest.raises(ContractError, match="parent fold/dataset"):
        case.engine.build_split(
            other.fingerprint, replace(definition, parent_fold_id=parent.fold_ids[0])
        )
    from examples.feature_store_demo import definition as feature_definition

    feature = feature_definition("market.foreign_preprocessing")
    spec = replace(
        case.fixture.preprocessing,
        normalization=replace(case.fixture.preprocessing.normalization, feature=feature),
    )
    with case.repository.transaction():
        case.repository.put(feature)
        case.repository.put(spec)
    with pytest.raises(ContractError, match="exact dataset feature set"):
        case.engine.build_split(
            case.dataset.fingerprint,
            replace(definition, preprocessing_spec_ids=(spec.fingerprint,)),
        )
