"""Exact causal grids, compatibility failures, missing traces and immutable revisions."""

import json
from dataclasses import replace

import pytest

from afre.feature_store import FeatureSetManifest
from afre.feature_store.materialization import PointInTimeJoinResult
from afre.feature_store.models import AvailabilityEvidence
from afre.features import MissingState
from afre.research_datasets import (
    DatasetCompleteness,
    DatasetMissingPolicy,
    ResearchInputBuild,
    ResearchSelection,
    SampleState,
)
from afre.research_datasets.materialization import (
    completeness_of,
    sample_from,
    validate_selection,
)
from afre.research_datasets.validation import validate_links
from afre.schema import ContractError
from afre.serialization import canonical_json, deserialize
from afre.universe.models import UniverseSnapshot
from examples.feature_store_demo import clocks, source_vintage
from examples.universe_demo import SECURITIES
from tests.research_datasets.conftest import Case


def test_exact_grid_and_causal_evidence(case: Case) -> None:
    samples = case.engine.dataset_samples(case.dataset.fingerprint)
    assert len(samples) == 8 * 4 * 2
    assert len({(s.timestamp_ns, s.security, s.target_definition_id) for s in samples}) == len(
        samples
    )
    assert case.dataset.completeness is DatasetCompleteness.KNOWN_GAPS
    for sample in samples:
        assert deserialize(canonical_json(sample)) == sample
        if sample.join_id:
            join = case.repository.get(PointInTimeJoinResult, sample.join_id)
            assert all(
                a.selected is None
                or a.selected.clocks.final_available_ns <= sample.timestamp_ns
                for a in join.audits
            )
        assert sample.feature_set_id == case.fixture.definition.feature_set.fingerprint
    assert any(s.state is SampleState.FEATURE_INCOMPLETE for s in samples)
    audit = case.engine.audit_dataset(case.dataset.fingerprint)
    assert "causal-features" in audit.checks and audit.exclusion_ids
    assert case.repository.audit() > 100


def test_historical_delisted_and_ticker_reuse(case: Case) -> None:
    samples = case.engine.dataset_samples(case.dataset.fingerprint)
    assert any(
        s.security == SECURITIES[2]
        and s.timestamp_ns == 10
        and s.state is SampleState.AVAILABLE
        for s in samples
    )
    assert all(
        s.state is SampleState.INELIGIBLE
        for s in samples
        if s.security == SECURITIES[2] and s.timestamp_ns >= 60
    )
    assert all(
        s.state is SampleState.INELIGIBLE
        for s in samples
        if s.security == SECURITIES[3] and s.timestamp_ns < 60
    )
    assert any(
        s.security == SECURITIES[3]
        and s.timestamp_ns == 70
        and s.state is SampleState.AVAILABLE
        for s in samples
    )


@pytest.mark.parametrize(
    "policy",
    [
        DatasetMissingPolicy.FAIL,
        DatasetMissingPolicy.DROP_SAMPLE,
        DatasetMissingPolicy.PRESERVE_MISSING,
    ],
)
def test_missing_policy(case: Case, policy: DatasetMissingPolicy) -> None:
    definition = replace(case.fixture.definition, missing_policy=policy)
    if policy is DatasetMissingPolicy.FAIL:
        with pytest.raises(ContractError, match="FAIL"):
            case.engine.build_dataset(definition, case.fixture.requests, 100, 100)
        return
    dataset = case.engine.build_dataset(definition, case.fixture.requests, 100, 100)
    samples = case.engine.dataset_samples(dataset.fingerprint)
    absent = tuple(s for s in samples if s.state is not SampleState.AVAILABLE)
    assert absent and all(
        s.dropped == (policy is DatasetMissingPolicy.DROP_SAMPLE) for s in absent
    )
    assert set(s.fingerprint for s in absent) <= set(
        case.engine.audit_dataset(dataset.fingerprint).exclusion_ids
    )


def test_frozen_revision_and_export(case: Case) -> None:
    old = case.engine.export_rows(case.dataset.fingerprint, 100)
    feature = case.fixture.preprocessing.normalization.feature
    previous = source_vintage(feature, 10, 10, 10.0, entity=SECURITIES[0].instrument)
    revised = replace(previous, value=999.0, predecessor_id=previous.fingerprint)
    with case.repository.transaction():
        case.repository.put(revised)
    rebuilt = case.engine.build_dataset(
        case.fixture.definition, tuple(reversed(case.fixture.requests)), 100, 100
    )
    assert rebuilt.fingerprint != case.dataset.fingerprint
    assert case.engine.export_rows(case.dataset.fingerprint, 100) == old
    before_truth = json.loads(case.engine.export_rows(case.dataset.fingerprint, 10))
    assert all(
        cell["data"]["value"] is None
        for row in before_truth["rows"]
        for cell in row["cells"].values()
        if cell["role"] == "target"
    )
    case.engine.audit_dataset(case.dataset.fingerprint)


def test_provider_publication_does_not_backdate_feature(case: Case) -> None:
    feature = case.fixture.preprocessing.normalization.feature
    vintage = source_vintage(feature, 9, 12, 777.0, entity=SECURITIES[1].instrument)
    vintage = replace(
        vintage,
        clocks=AvailabilityEvidence(
            12, 12, 12, 12, upstream_publication_ns=9, upstream_available_ns=9
        ),
    )
    with case.repository.transaction():
        case.repository.put(vintage)
    rebuilt = case.engine.build_dataset(
        case.fixture.definition, case.fixture.requests, 100, 100
    )
    sample = next(
        s
        for s in case.engine.dataset_samples(rebuilt.fingerprint)
        if s.timestamp_ns == 10 and s.security == SECURITIES[1]
    )
    assert sample.state is SampleState.FEATURE_INCOMPLETE


def test_sample_tamper_and_missing_target(case: Case) -> None:
    repository = case.repository
    samples = case.engine.dataset_samples(case.dataset.fingerprint)
    selected = next(s for s in samples if s.state is SampleState.AVAILABLE)
    with repository.transaction(), repository.validation_cache():
        with pytest.raises(ContractError, match="deterministic"):
            repository.put(replace(selected, target_available_ns=selected.timestamp_ns))
        selection = repository.resolve(ResearchSelection, selected.selection_id)
        build = repository.resolve(ResearchInputBuild, selected.input_build_id)
        missing = replace(selection, request=replace(selection.request, target_dataset_id=None))
        sample = sample_from(
            repository,
            case.fixture.definition,
            build,
            missing,
            case.fixture.definition.target_set.definitions[0],
        )
        assert sample.state is SampleState.TARGET_NOT_AVAILABLE_YET and sample.target_id is None
        with pytest.raises(ContractError, match="selection"):
            validate_links(repository, replace(selected, selection_id=missing.fingerprint))


def test_selection_mismatch(case: Case) -> None:
    sample = next(
        s
        for s in case.engine.dataset_samples(case.dataset.fingerprint)
        if s.state is SampleState.AVAILABLE
    )
    with case.repository.read_snapshot(), case.repository.validation_cache():
        selection = case.repository.resolve(ResearchSelection, sample.selection_id)
        with pytest.raises(ContractError, match="temporal"):
            validate_selection(
                case.repository,
                replace(
                    selection,
                    timestamp_ns=selection.timestamp_ns + 1,
                    origin=None,
                    join_id=None,
                ),
                case.fixture.definition,
            )
        with pytest.raises(ContractError, match="group"):
            validate_selection(
                case.repository, replace(selection, group_keys=()), case.fixture.definition
            )
        with pytest.raises(ContractError, match="join"):
            validate_selection(
                case.repository,
                replace(selection, origin=None, join_id=None),
                case.fixture.definition,
            )
        snapshot = case.repository.resolve(UniverseSnapshot, selection.request.snapshot_id)
        assert snapshot.valid_at_ns == sample.timestamp_ns


def test_dataset_idempotence_and_unknown_completeness(case: Case) -> None:
    assert (
        case.engine.build_dataset(case.fixture.definition, case.fixture.requests, 100, 100)
        == case.dataset
    )
    samples = case.engine.dataset_samples(case.dataset.fingerprint)
    assert (
        completeness_of((next(s for s in samples if s.state is SampleState.AVAILABLE),))
        is DatasetCompleteness.COMPLETE
    )
    assert (
        completeness_of((replace(samples[0], state=SampleState.UNIVERSE_UNKNOWN),))
        is DatasetCompleteness.UNKNOWN
    )
    assert (
        FeatureSetManifest(case.fixture.definition.feature_set.definitions)
        == case.fixture.definition.feature_set
    )
    assert MissingState.NOT_AVAILABLE_YET.value in case.engine.export_rows(
        case.dataset.fingerprint, 10
    )


def test_universe_future_knowledge_rejected_and_unknown_grid_retained(case: Case) -> None:
    from afre.universe import ConstituentCoverage, UniverseEngine
    from afre.universe.schema import SnapshotCompleteness

    first = case.repository.get(UniverseSnapshot, case.fixture.requests[0].snapshot_id)
    universe_engine = UniverseEngine(case.repository)
    future = universe_engine.universe_as_of(first.definition, 10, 20)
    universe_engine.persist_snapshot(future)
    request = replace(
        case.fixture.requests[0], snapshot_id=future.fingerprint, target_dataset_id=None
    )
    with pytest.raises(ContractError, match="future knowledge"):
        case.engine.build_dataset(case.fixture.definition, (request,), 100, 100)
    assert first.coverage_id is not None
    coverage = case.repository.get(ConstituentCoverage, first.coverage_id)
    revised = replace(
        coverage,
        completeness=SnapshotCompleteness.UNKNOWN,
        evidence=replace(
            coverage.evidence, predecessor_id=coverage.fingerprint, clocks=clocks(10)
        ),
    )
    with case.repository.transaction():
        case.repository.put(revised)
    unknown = universe_engine.universe_as_of(first.definition, 10, 10)
    universe_engine.persist_snapshot(unknown)
    request = replace(request, snapshot_id=unknown.fingerprint)
    dataset = case.engine.build_dataset(case.fixture.definition, (request,), 100, 100)
    assert dataset.completeness is DatasetCompleteness.UNKNOWN
    samples = case.engine.dataset_samples(dataset.fingerprint)
    assert len(samples) == 8 and any(s.state is SampleState.UNIVERSE_UNKNOWN for s in samples)
    assert all(s.origin is None and s.join_id is None for s in samples)
    case.engine.audit_dataset(dataset.fingerprint)


def test_target_correction_changes_new_dataset_and_preserves_old_truth(case: Case) -> None:
    from afre.target_engine import TargetBar, TargetDatasetManifest, TargetEngine
    from examples.target_demo import CALENDAR_TARGET, SOURCE_MARKET

    original = case.engine.export_rows(case.dataset.fingerprint, 100)
    request = case.fixture.requests[0]
    assert request.target_dataset_id is not None
    labels = case.repository.get(TargetDatasetManifest, request.target_dataset_id)
    from afre.target_engine.models import TargetVintage

    row = case.repository.get(TargetVintage, labels.row_ids[0])
    assert row.endpoint_bar_id is not None
    old = case.repository.get(TargetBar, row.endpoint_bar_id)
    revised = replace(old, close=1000.0, clocks=clocks(100), predecessor_id=old.fingerprint)
    with case.repository.transaction():
        case.repository.put(revised)
    targets = TargetEngine(case.repository)
    source = targets.freeze_source(SOURCE_MARKET, CALENDAR_TARGET, 100)
    corrected = targets.build_dataset(
        "research-targets-corrected",
        labels.origins,
        labels.targets,
        source.fingerprint,
        labels.universe,
        clocks(100),
    )
    requests = (
        replace(request, target_dataset_id=corrected.fingerprint),
        *case.fixture.requests[1:],
    )
    dataset = case.engine.build_dataset(case.fixture.definition, requests, 100, 100)
    assert dataset.fingerprint != case.dataset.fingerprint
    assert case.engine.export_rows(case.dataset.fingerprint, 100) == original
    assert case.engine.export_rows(dataset.fingerprint, 100) != original
    case.engine.audit_dataset(case.dataset.fingerprint)


def test_wrong_target_snapshot_fails(case: Case) -> None:
    wrong = replace(
        case.fixture.requests[0], target_dataset_id=case.fixture.requests[1].target_dataset_id
    )
    with pytest.raises(ContractError, match="universe mismatch"):
        case.engine.build_dataset(case.fixture.definition, (wrong,), 100, 100)


def test_full_information_interval_includes_dependency_and_reference_bar(case: Case) -> None:
    from afre.feature_store import FeatureStore
    from afre.feature_store.dag import Transformation
    from afre.feature_store.providers import (
        BarTimestampConvention,
        MarketBar,
        MarketFeatureAdapter,
    )
    from afre.research_datasets.materialization import feature_start
    from afre.time import TimeRange
    from examples.feature_store_demo import (
        BUILD,
        CALENDAR,
        SOURCE,
        computation,
        definition,
        origin,
    )

    feature = definition(lookback_ns=0)
    derived = definition("market.derived_test", dependencies=(feature,), lookback_ns=0)
    bar = MarketBar(
        SECURITIES[0].instrument,
        TimeRange(5, 10),
        10,
        BarTimestampConvention.END_EXCLUSIVE,
        100.0,
        10.0,
        clocks(10),
        SOURCE,
        feature.adjustment,
        CALENDAR,
        BUILD,
    )
    vintage = MarketFeatureAdapter().extract(bar, feature)
    with case.repository.transaction():
        for value in (feature, derived, bar, vintage.source, vintage):
            case.repository.put(value)
    value, _ = FeatureStore(case.repository).compute(
        computation(derived, (feature,), Transformation.IDENTITY), origin(30), clocks(30)
    )
    with case.repository.read_snapshot(), case.repository.validation_cache():
        assert feature_start(case.repository, value) == 5
        assert feature_start(case.repository, value) == 5


def test_each_sample_has_frozen_audit_and_fold_admission_evidence(case: Case) -> None:
    from afre.research_datasets import Partition
    from examples.research_dataset_demo import split_definition

    rows = case.repository._connection.execute(
        "SELECT count(*) FROM r_artifacts WHERE type_name='SampleContaminationAudit'"
    ).fetchone()
    assert rows[0] == len(case.dataset.sample_ids)
    split = case.engine.build_split(case.dataset.fingerprint, split_definition(case.fixture))
    train = case.engine.training_samples_for_fold(split.fold_ids[0])[0]
    audit = case.engine.audit_sample(
        case.dataset.fingerprint, train.fingerprint, split.fold_ids[0]
    )
    assert audit.partition is Partition.TRAIN and "target-known-by-cutoff" in audit.checks
    assert train.target_id in audit.evidence_ids
    missing = next(
        s
        for s in case.engine.dataset_samples(case.dataset.fingerprint)
        if s.state is SampleState.INELIGIBLE
    )
    assert (
        case.engine.audit_sample(case.dataset.fingerprint, missing.fingerprint).state
        is SampleState.INELIGIBLE
    )
    with case.repository.transaction(), pytest.raises(ContractError, match="audit evidence"):
        case.repository.put(replace(audit, checks=("incomplete-check",)))
    case.repository.audit()


def test_export_preserves_known_missing_truth_and_typed_groups(case: Case) -> None:
    sample = next(
        s
        for s in case.engine.dataset_samples(case.dataset.fingerprint)
        if s.state is SampleState.TARGET_MISSING
    )
    output = json.loads(case.engine.export_rows(case.dataset.fingerprint, 100))
    row = next(r for r in output["rows"] if r["sample_id"] == sample.fingerprint)
    target = next(
        t
        for t in case.fixture.definition.target_set.definitions
        if t.fingerprint == sample.target_definition_id
    )
    cell = row["cells"][target.name]["data"]
    assert cell["missing_state"] == MissingState.MISSING.value
    assert cell["value"] is None and not cell["target_known_by_cutoff"]
    assert row["cells"]["group.issuer"]["role"] == "metadata"
    assert row["cells"]["group.issuer"]["data"] == dict(sample.group_keys)["issuer"]
