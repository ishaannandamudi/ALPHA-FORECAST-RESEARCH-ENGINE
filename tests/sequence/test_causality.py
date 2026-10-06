"""Held-out perturbations, target-free application and actual construction clocks."""

from dataclasses import replace
from typing import TypeVar

import pytest

from afre.nonlinear import ScalarFeatureDefinition, ScalarInput
from afre.research_datasets.samples import ResearchSample
from afre.schema import Artifact, ContractError
from afre.sequence import (
    SequenceModelArtifact,
    SequenceObservation,
    SequenceSnapshot,
    SequenceTransformArtifact,
)
from afre.serialization import canonical_json
from afre.target_engine.definitions import TargetDefinition
from afre.target_engine.models import TargetVintage
from tests.sequence.conftest import Case

A = TypeVar("A", bound=Artifact)


def test_heldout_values_and_labels_do_not_fit(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, model = case.fixture.specs[0], case.fixture.models[0]
    old_state = case.repo.get(SequenceTransformArtifact, model.transform_id)
    case.observe(55, 1e6)
    case.observe(90, -1e6)
    original = case.repo.get
    heldout = {
        case.repo.get(ResearchSample, sid).target_id
        for sid, _ in (*case.fixture.validation, *case.fixture.test)
    }

    def perturbed(cls: type[A], identity: str) -> A:
        value = original(cls, identity)
        if identity in heldout and isinstance(value, TargetVintage):
            return replace(value, value=100.0)
        return value

    monkeypatch.setattr(case.repo, "get", perturbed)
    for _, identity in case.fixture.bindings:
        snapshot = case.repo.get(SequenceSnapshot, identity)
        assert case.engine.snapshot(snapshot.origin, spec.features, spec.window, 40) == snapshot
    assert case.engine.fit_transform(spec, case.fixture.bindings, 40, 40, 40) == old_state
    assert case.engine.fit(spec, model.dataset_id, 40, 40, 40) == model


def test_target_free_predict_is_enforced(case: Case, monkeypatch: pytest.MonkeyPatch) -> None:
    forecast = case.forecast
    before = canonical_json(case.fixture.models[0])
    original = case.repo.get

    def checked(cls: type[A], identity: str) -> A:
        assert cls is not TargetVintage
        return original(cls, identity)

    monkeypatch.setattr(case.repo, "get", checked)
    assert (
        case.engine.predict(
            forecast.model_id,
            forecast.sample_id,
            forecast.snapshot_id,
            60,
            forecast.probability.base_forecast_id if forecast.probability else None,
        )
        == forecast
    )
    with case.repo.feature_only(), pytest.raises(ContractError, match="truth"):
        original(TargetVintage, "afre.target_vintage:1.0:" + "1" * 64)
    assert canonical_json(case.repo.get(SequenceModelArtifact, forecast.model_id)) == before


def test_no_reconstruction_clock_backdating(case: Case) -> None:
    f = case.forecast
    s = case.repo.get(SequenceSnapshot, f.snapshot_id)
    rebuilt = case.engine.snapshot(
        s.origin, case.fixture.features, case.fixture.specs[0].window, 100, s.candidate_ids
    )
    assert rebuilt.available_ns == 100
    with pytest.raises(ContractError, match="computation"):
        case.engine.predict(f.model_id, f.sample_id, rebuilt.fingerprint, 60)
    with pytest.raises(ContractError):
        case.engine.predict(f.model_id, f.sample_id, f.snapshot_id, 61)


def test_neutral_cross_domain_histories(case: Case) -> None:
    sources = [
        case.repo.get_any(case.repo.get(SequenceObservation, i).source_id)
        for i in case.fixture.observation_ids
    ]
    kinds = {s.definition.kind.value for s in sources if isinstance(s, ScalarInput)}
    assert {
        "feature",
        "external_signal",
        "event_attribute",
        "regime_probability",
        "expert_point",
    } <= kinds
    names = {
        s.definition.source_key[3]
        for s in sources
        if isinstance(s, ScalarInput) and s.definition.kind.value == "external_signal"
    }
    assert {"microstructure.signal", "context.signal", "options.skew"} <= names
    assert any(s.domain == "nl_value" for s in sources)


def test_exact_complete_train_required(case: Case) -> None:
    with pytest.raises(ContractError, match="complete TRAIN"):
        case.engine.fit_transform(case.fixture.specs[0], case.fixture.bindings[:-1], 40, 40, 40)
    with pytest.raises(ContractError, match="bounds/duplicates"):
        case.engine.fit_transform(
            case.fixture.specs[0],
            (*case.fixture.bindings, case.fixture.bindings[0]),
            40,
            40,
            40,
        )


def test_source_correction_retains_old_bytes(case: Case) -> None:
    f = case.forecast
    snap = case.repo.get(SequenceSnapshot, f.snapshot_id)
    before = canonical_json(snap)
    revised = case.observe(20, 12.0, received=59)
    rebuilt = case.engine.snapshot(
        snap.origin, case.fixture.features, case.fixture.specs[0].window, 60
    )
    assert rebuilt.fingerprint != snap.fingerprint
    assert revised.fingerprint in {i for row in rebuilt.observation_ids for i in row}
    assert canonical_json(case.repo.get(SequenceSnapshot, snap.fingerprint)) == before


def test_expert_target_mismatch(case: Case) -> None:
    spec = case.fixture.specs[0]
    # A separate valid target identity cannot reuse native experts for a different horizon.
    native = next(
        f
        for f in spec.features
        if f.source_definition_id.startswith("afre.nl_feature:")
        and case.repo.get(ScalarFeatureDefinition, f.source_definition_id).kind.value
        == "expert_point"
    )
    assert native in spec.features
    targets = case.repo._connection.execute(
        "SELECT fingerprint FROM target_artifacts WHERE type_name='TargetDefinition'"
    ).fetchall()
    other = next(
        (case.repo.get_any(r[0]) for r in targets if r[0] != spec.target.fingerprint), None
    )
    if other is not None:
        assert isinstance(other, TargetDefinition)
        with pytest.raises(ContractError):
            case.engine.fit_transform(
                replace(spec, target=other), case.fixture.bindings, 40, 40, 40
            )


def test_candidate_metadata_cannot_backdate_construction(case: Case) -> None:
    future = case.observe(20, 2.0, received=70)
    spec = case.fixture.specs[0]
    with pytest.raises(ContractError, match="candidate evidence unavailable"):
        case.engine.snapshot(
            case.forecast.origin, (case.micro,), spec.window, 60, (future.fingerprint,)
        )
    current = case.engine.snapshot(case.forecast.origin, (case.micro,), spec.window, 60)
    assert future.fingerprint not in current.candidate_ids
    audited = case.engine.snapshot(case.forecast.origin, (case.micro,), spec.window, 70)
    assert audited.available_ns == 70
    assert (future.fingerprint, "future-availability") in audited.exclusions


def test_mixture_output_actual_processing_clock(case: Case) -> None:
    from afre.mixture import MixtureForecast
    from afre.nonlinear import NonlinearEngine
    from afre.sequence import SequenceFeatureDefinition

    mixture = case.repo.get(MixtureForecast, case.fixture.upstream.upstream.forecast_ids[0])
    scalar = NonlinearEngine(case.repo).scalar(mixture.fingerprint, mixture.origin)
    feature = SequenceFeatureDefinition(
        scalar.definition.fingerprint, "mixture.history", "1", scalar.definition.unit
    )
    observation = case.engine.observation(feature, scalar.fingerprint)
    assert observation.afre_ready_ns >= mixture.request.computed_ns
    window = case.fixture.specs[0].window
    snapshot = case.engine.snapshot(
        mixture.origin,
        (feature,),
        window,
        mixture.origin.timestamp_ns,
        (observation.fingerprint,),
    )
    assert observation.value in {row[0] for row in snapshot.values}
