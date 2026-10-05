"""Data-only providers, six clocks, qualified reconstruction and ordinary feature bridge."""

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from afre.cross_sectional import ScoreSource, ScoreSpec, SignalQuality, signal_feature
from afre.cross_sectional.artifacts import CrossSectionObservation
from afre.cross_sectional.queries import external_as_of, group_as_of
from afre.cross_sectional.scoring import score_for
from afre.feature_store.models import AvailabilityEvidence, QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind
from afre.features import MissingState, ValueType
from afre.schema import ContractError
from examples.cross_sectional_demo import external, group, provider_source
from examples.feature_store_demo import definition
from tests.cross_sectional.conftest import Case


@pytest.mark.parametrize("quality", list(SignalQuality))
def test_external_quality(case: Case, quality: SignalQuality) -> None:
    f = case.fixture
    e = f.ranking.entries[0]
    s = replace(
        external(e.security, 60, 3.0),
        quality=quality,
        value=3.0 if quality in (SignalQuality.VALID, SignalQuality.DEGRADED) else None,
    )
    identity = case.engine.publish_external(s)
    o = replace(case.repo.get(CrossSectionObservation, e.observation_id), source_id=identity)
    raw = score_for(case.repo, f.spec, o)
    assert (raw.value is not None) == (quality is SignalQuality.VALID)
    registered = replace(
        definition(s.signal_name, "dimensionless"), source_dataset_ids=(s.source.dataset_id,)
    )
    vintage = signal_feature(s, registered)
    assert (vintage.state is MissingState.PRESENT) == (quality is SignalQuality.VALID)


@pytest.mark.parametrize(
    "field",
    ["provider_version", "provider_schema", "signal_version", "signal_semantics", "unit"],
)
def test_external_identity_versions(case: Case, field: str) -> None:
    security = case.fixture.ranking.entries[0].security
    original = external(security, 60, 3.0)
    if field == "provider_version":
        changed = replace(original, provider_version="2", source=provider_source(version="2"))
    elif field == "provider_schema":
        changed = replace(original, provider_schema="changed")
    elif field == "signal_version":
        changed = replace(original, signal_version="changed")
    elif field == "signal_semantics":
        changed = replace(original, signal_semantics="changed")
    else:
        changed = replace(original, unit="changed")
    assert original.fingerprint != changed.fingerprint


def test_source_event_does_not_establish_receipt(case: Case) -> None:
    f = case.fixture
    e = f.ranking.entries[0]
    clocks = AvailabilityEvidence(
        62, 62, 62, 62, upstream_publication_ns=60, upstream_available_ns=60
    )
    s = replace(external(e.security, 60, 3.0), clocks=clocks)
    identity = case.engine.publish_external(s)
    sources = tuple(
        (key, identity if key == e.security.fingerprint else value) for key, value in f.sources
    )
    rank = case.engine.build_ranking(f.spec, sources, f.group_refs)
    assert next(row for row in rank.entries if row.security == e.security).rank is None


def test_archive_requires_qualified_historical_delivery(case: Case) -> None:
    f = case.fixture
    e = f.ranking.entries[0]
    s = external(e.security, 60, 3.0, 200)
    s = replace(
        s,
        clocks=replace(
            s.clocks,
            upstream_publication_ns=60,
            upstream_available_ns=60,
            mode=AvailabilityMode.RECONSTRUCTED,
        ),
    )
    identity = case.engine.publish_external(s)
    o = replace(case.repo.get(CrossSectionObservation, e.observation_id), source_id=identity)
    assert score_for(case.repo, f.spec, o).value is None
    proof = QualifiedHistoricalDelivery(
        s.source.fingerprint,
        e.security.instrument,
        DeliveryEvidenceKind.QUALIFIED_CHANNEL_REPLAY,
        60,
        60,
        60,
        200,
        "local-replay-attestor",
        "qualified-delivery-channel",
        "1",
        s.source.provenance,
    )
    qualified = replace(
        s, clocks=replace(s.clocks, final_available_ns=60, historical_delivery=proof)
    )
    identity = case.engine.publish_external(qualified)
    o = replace(o, source_id=identity)
    with pytest.raises(ContractError, match="locally approved"):
        score_for(case.repo, f.spec, o)
    spec = replace(f.spec, approved_delivery_attestors=("local-replay-attestor",))
    o = replace(o, spec_id=spec.fingerprint)
    assert score_for(case.repo, spec, o).value == 3.0
    assert (
        qualified.clocks.afre_received_ns == 200 and qualified.clocks.final_available_ns == 60
    )


@pytest.mark.parametrize(
    "kind", ["execution", "provider", "as-of", "value", "feature-unit", "feature-type"]
)
def test_external_rejects_bad_contract(kind: str, case: Case) -> None:
    s = external(case.fixture.ranking.entries[0].security, 60, 3.0)
    with pytest.raises(ContractError):
        if kind == "execution":
            replace(s, signal_name="microstructure.order_id")
        elif kind == "provider":
            replace(s, provider_name="other-provider")
        elif kind == "as-of":
            replace(s, as_of_ns=61)
        elif kind == "value":
            replace(s, quality=SignalQuality.MISSING)
        else:
            registered = replace(
                definition(s.signal_name, "dimensionless"),
                source_dataset_ids=(s.source.dataset_id,),
            )
            if kind == "feature-unit":
                registered = replace(
                    registered, definition=replace(registered.definition, unit="different")
                )
            else:
                registered = replace(
                    registered,
                    definition=replace(registered.definition, value_type=ValueType.TEXT),
                )
            signal_feature(s, registered)


def test_categorical_external_state_as_feature(case: Case) -> None:
    s = replace(
        external(case.fixture.ranking.entries[0].security, 60, 3.0),
        signal_name="microstructure.external_state",
        signal_semantics="categorical-provider-state-v1",
        value="neutral-state",
        unit="category",
    )
    registered = definition(s.signal_name, "category")
    registered = replace(
        registered,
        definition=replace(registered.definition, value_type=ValueType.TEXT),
        source_dataset_ids=(s.source.dataset_id,),
    )
    assert signal_feature(s, registered).value == "neutral-state"
    identity = case.engine.publish_external(s)
    score = replace(
        case.fixture.spec.score,
        signal_name=s.signal_name,
        signal_semantics=s.signal_semantics,
        unit=s.unit,
    )
    spec = replace(case.fixture.spec, score=score)
    o = replace(
        case.repo.get(CrossSectionObservation, case.fixture.ranking.entries[0].observation_id),
        source_id=identity,
        spec_id=spec.fingerprint,
    )
    assert score_for(case.repo, spec, o).value is None


def test_indexed_external_and_group_lookup(case: Case) -> None:
    f = case.fixture
    e = next(e for e in f.ranking.entries if e.rank is not None)
    assert external_as_of(case.repo, f.spec.score, e.security, 60, 59) is None
    assert external_as_of(case.repo, f.spec.score, e.security, 60, 60) is not None
    changed = case.engine.publish_external(external(e.security, 60, 9.0))
    with pytest.raises(ContractError, match="ambiguous"):
        external_as_of(case.repo, f.spec.score, e.security, 60, 60)
    assert changed != dict(f.sources)[e.security.fingerprint]
    assert f.spec.group is not None
    assert group_as_of(case.repo, f.spec.group, e.security, 60, 60) is not None
    assert (
        group_as_of(case.repo, replace(f.spec.group, version="2"), e.security, 60, 60) is None
    )
    case.engine.publish_group(group(e.security, "corrected"))
    with pytest.raises(ContractError, match="ambiguous"):
        group_as_of(case.repo, f.spec.group, e.security, 60, 60)
    with pytest.raises(ContractError, match="external lookup"):
        external_as_of(
            case.repo,
            ScoreSpec(
                ScoreSource.POINT_PREDICTION,
                model_id=f.upstream.spec.bindings[0].point_model_id,
            ),
            e.security,
            60,
            60,
        )


def test_no_external_engine_or_executable_dependency() -> None:
    root = Path(__file__).resolve().parents[2] / "src/afre"
    prohibited = {
        "ame",
        "axiom_microstructure_engine",
        "pickle",
        "joblib",
        "subprocess",
        "socket",
    }
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not prohibited & {a.name.split(".")[0] for a in node.names}
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in prohibited
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "__import__"}
