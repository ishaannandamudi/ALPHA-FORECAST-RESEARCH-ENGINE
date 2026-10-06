"""TRAIN/TEST boundaries, receipt evidence and target-free immutable application."""

from dataclasses import replace
from typing import TypeVar

import pytest

from afre.cross_sectional.engine import CrossSectionEngine
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.schema import SignalQuality
from afre.feature_store.models import AvailabilityEvidence, QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind
from afre.lineage import ProvenanceRef
from afre.nonlinear import (
    FittedTransformArtifact,
    InteractionDefinition,
    InteractionMatrix,
    InteractionTrainingRow,
    NonlinearForecast,
    NonlinearInput,
    ScalarSourceKind,
)
from afre.research_datasets.splits import TestEvaluation as SealEvidence
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.target_engine.models import TargetVintage
from tests.nonlinear.conftest import Case


@pytest.mark.parametrize("partition", ["validation", "test"])
def test_heldout_cannot_fit_knots_or_matrix(case: Case, partition: str) -> None:
    ids = case.fixture.validation_ids if partition == "validation" else case.fixture.test_ids
    spec = case.fixture.specs[0]
    piece = next(d for d in spec.interaction_set.definitions if d.interaction_id == "piecewise")
    with pytest.raises(ContractError, match="TRAIN"):
        case.engine.fit_transform(spec, piece, ids, 40, 40, 40)
    with pytest.raises(ContractError, match="TRAIN"):
        case.engine.matrix(spec, ids, case.fixture.models[0].transform_ids, 40)


def test_heldout_truth_and_feature_perturbation_does_not_fit(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = case.fixture.models[2]
    matrix = case.repo.get(InteractionMatrix, model.matrix_id)
    admitted = {r.target_id for r in matrix.rows}
    A = TypeVar("A", bound=Artifact)
    original = case.repo.get

    def perturb(cls: type[A], identity: str) -> A:
        value = original(cls, identity)
        if isinstance(value, TargetVintage) and identity not in admitted:
            return replace(value, value=999.0)
        return value

    monkeypatch.setattr(case.repo, "get", perturb)
    refit = case.engine.fit(case.fixture.specs[2], matrix.fingerprint, 40, 40, 40)
    assert refit == model
    state = case.repo.get(FittedTransformArtifact, case.fixture.models[0].transform_ids[0])
    spec = case.fixture.specs[0]
    definition = case.repo.get(InteractionDefinition, state.definition_id)
    assert (
        case.engine.fit_transform(spec, definition, case.fixture.train_ids, 40, 40, 40) == state
    )


def test_target_free_prediction_transform_and_immutability(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    A = TypeVar("A", bound=Artifact)
    original = case.repo.get
    before = {
        i: canonical_json(case.repo.get_any(i))
        for i in (
            case.forecast.model_id,
            case.inputs.fingerprint,
            *(s.source_id for s in case.inputs.scalars),
        )
    }

    def guard(cls: type[A], identity: str) -> A:
        assert cls not in (TargetVintage, InteractionMatrix, InteractionTrainingRow), (
            "prediction read TRAIN/truth"
        )
        return original(cls, identity)

    monkeypatch.setattr(case.repo, "get", guard)
    for model, ids in zip(case.fixture.models, case.fixture.forecast_ids, strict=True):
        forecast = case.repo.get(NonlinearForecast, ids[0])
        assert (
            case.engine.predict(
                model.fingerprint,
                forecast.input_id,
                forecast.computed_ns,
                forecast.probability.base_forecast_id if forecast.probability else None,
            )
            == forecast
        )
    definition = case.fixture.specs[0].interaction_set.definitions[0]
    assert (
        case.engine.apply(
            definition, case.inputs.fingerprint, case.inputs.origin.timestamp_ns
        ).value
        is not None
    )
    assert {i: canonical_json(case.repo.get_any(i)) for i in before} == before


@pytest.mark.parametrize("time", [59, 61])
def test_actual_computation_cannot_backdate_or_follow_origin(case: Case, time: int) -> None:
    with pytest.raises(ContractError):
        case.engine.predict(case.forecast.model_id, case.inputs.fingerprint, time)


def test_future_model_and_transform(case: Case) -> None:
    old = case.fixture.models[0]
    future = case.engine.fit(case.fixture.specs[0], old.matrix_id, 70, 70, 70)
    with pytest.raises(ContractError, match="unavailable"):
        case.engine.predict(future.fingerprint, case.inputs.fingerprint, 60)
    state = case.repo.get(FittedTransformArtifact, old.transform_ids[0])
    spec = case.fixture.specs[0]
    definition = case.repo.get(InteractionDefinition, state.definition_id)
    later = case.engine.fit_transform(spec, definition, case.fixture.train_ids, 70, 70, 70)
    with pytest.raises(ContractError, match="precedes"):
        case.engine.apply(definition, case.inputs.fingerprint, 60, later.fingerprint)


@pytest.mark.parametrize("received", [62, 1_000_000])
def test_publication_is_not_received_availability(case: Case, received: int) -> None:
    scalar = next(
        s for s in case.inputs.scalars if s.definition.kind is ScalarSourceKind.EXTERNAL_SIGNAL
    )
    source = case.repo.get(ExternalSignal, scalar.source_id)
    late = replace(
        source, clocks=AvailabilityEvidence(received, received, received, received, 60, 60)
    )
    CrossSectionEngine(case.repo).publish_external(late)
    with pytest.raises(ContractError, match="unavailable"):
        case.engine.scalar(late.fingerprint, scalar.origin)
    with pytest.raises(ContractError, match="backdated"):
        replace(late.clocks, final_available_ns=60)


def test_qualified_reconstruction_preserves_actual_later_clocks(case: Case) -> None:
    scalar = next(
        s for s in case.inputs.scalars if s.definition.kind is ScalarSourceKind.EXTERNAL_SIGNAL
    )
    source = case.repo.get(ExternalSignal, scalar.source_id)
    proof = QualifiedHistoricalDelivery(
        source.source.fingerprint,
        scalar.origin.instrument,
        DeliveryEvidenceKind.AFRE_DELIVERY_LOG,
        60,
        60,
        60,
        1_000_000,
        "approved-lab",
        "archive-log",
        "1",
        ProvenanceRef("lab", "receipt-log", "1", "0" * 64),
    )
    reconstructed = replace(
        source,
        clocks=AvailabilityEvidence(
            1_000_000, 1_000_000, 1_000_000, 60, 60, 60, AvailabilityMode.RECONSTRUCTED, proof
        ),
    )
    CrossSectionEngine(case.repo).publish_external(reconstructed)
    with pytest.raises(ContractError, match="unapproved"):
        case.engine.scalar(reconstructed.fingerprint, scalar.origin)
    qualified = case.engine.scalar(
        reconstructed.fingerprint, scalar.origin, approved_attestors=("approved-lab",)
    )
    assert qualified.available_ns == 60
    assert reconstructed.clocks.afre_received_ns == 1_000_000
    assert proof.historical_received_ns == 60
    packet = case.engine.input(
        case.inputs.sample_id,
        tuple(
            qualified.fingerprint if s == scalar else s.fingerprint for s in case.inputs.scalars
        ),
    )
    with pytest.raises(ContractError, match="attestors"):
        case.engine.predict(case.forecast.model_id, packet.fingerprint, 60)


def test_missing_tree_input_fails_explicitly(case: Case) -> None:
    scalar = next(
        s for s in case.inputs.scalars if s.definition.kind is ScalarSourceKind.EXTERNAL_SIGNAL
    )
    source = case.repo.get(ExternalSignal, scalar.source_id)
    missing = replace(source, value=None, quality=SignalQuality.MISSING)
    CrossSectionEngine(case.repo).publish_external(missing)
    absent = case.engine.scalar(missing.fingerprint, scalar.origin)
    packet = case.engine.input(
        case.inputs.sample_id,
        tuple(
            absent.fingerprint if s == scalar else s.fingerprint for s in case.inputs.scalars
        ),
    )
    assert absent.value is None
    with pytest.raises(ContractError, match="missing"):
        case.engine.predict(case.fixture.models[2].fingerprint, packet.fingerprint, 60)


def test_TEST_seals_reuse_and_calibration_boundary(case: Case) -> None:
    with pytest.raises(ContractError, match="TEST identity"):
        case.engine.evaluate(case.fixture.test_forecast_ids, 100, 100)
    first = case.engine.evaluate(
        case.fixture.test_forecast_ids, 100, 100, test_identity="nl-TEST-1"
    )
    assert (
        case.engine.evaluate(
            case.fixture.test_forecast_ids, 100, 100, test_identity="nl-TEST-1"
        )
        == first
    )
    second = case.engine.evaluate(
        case.fixture.test_forecast_ids, 100, 100, test_identity="nl-TEST-2"
    )
    assert (
        first.test_evaluation_id
        in case.repo.get(SealEvidence, second.test_evaluation_id or "").previous_evaluation_ids
    )
    with pytest.raises(ContractError, match="non-TEST"):
        case.engine.assess_calibration(
            case.forecast.fingerprint, case.fixture.test_forecast_ids, 100
        )
    assert (
        case.engine.assess_calibration(case.forecast.fingerprint, (), 100).status.value
        == "insufficient_data"
    )
    assert (
        case.engine.assess_calibration(
            case.forecast.fingerprint, case.fixture.forecast_ids[0], 100
        ).status.value
        == "unavailable"
    )


def test_training_model_cannot_issue_historical_train_forecast(case: Case) -> None:
    packet = case.repo.get(NonlinearInput, case.fixture.train_ids[0])
    with pytest.raises(ContractError, match="held-out"):
        case.engine.predict(
            case.fixture.models[0].fingerprint, packet.fingerprint, packet.origin.timestamp_ns
        )
