"""Exact model/law/state compatibility and independent stability arithmetic."""

from dataclasses import replace
from typing import TypeVar

import pytest

from afre.mixture import MixtureForecast
from afre.nonlinear import (
    FittedTransformArtifact,
    InteractionDefinition,
    InteractionMissingPolicy,
    InteractionStability,
    InteractionTransform,
    NonlinearEvaluation,
    NonlinearForecast,
    NonlinearModelArtifact,
    NonlinearProbabilityView,
    ScalarSourceKind,
)
from afre.nonlinear.stability import stability_for
from afre.schema import Artifact, ContractError
from tests.nonlinear.conftest import Case


def test_mixture_output_is_explicit_causal_scalar(case: Case) -> None:
    mixture = case.repo.get(MixtureForecast, case.fixture.upstream.forecast_ids[0])
    scalar = case.engine.scalar(mixture.fingerprint, mixture.origin)
    assert (
        scalar.definition.kind is ScalarSourceKind.MIXTURE_POINT
        and scalar.value == mixture.value
    )
    assert scalar.available_ns == mixture.available_ns


def test_exact_fitted_state_grid(case: Case) -> None:
    spec = case.fixture.specs[0]
    state = case.repo.get(FittedTransformArtifact, case.fixture.models[0].transform_ids[0])
    definition = case.repo.get(InteractionDefinition, state.definition_id)
    with pytest.raises(ContractError, match="state"):
        case.engine.apply(definition, case.inputs.fingerprint, 60)
    with pytest.raises(ContractError, match="grid"):
        case.engine.matrix(spec, case.fixture.train_ids, (), 40)
    with pytest.raises(ContractError, match="grid"):
        case.engine.matrix(
            spec, case.fixture.train_ids, (state.fingerprint, state.fingerprint), 40
        )
    other = case.fixture.models[1].transform_ids[0]
    with pytest.raises(ContractError, match="TRAIN/fold/cutoff"):
        case.engine.matrix(spec, case.fixture.train_ids, (other,), 40)


def test_state_and_target_mismatches(case: Case) -> None:
    state = case.repo.get(FittedTransformArtifact, case.fixture.models[0].transform_ids[0])
    fixed = next(
        d
        for d in case.fixture.specs[0].interaction_set.definitions
        if d.transform is InteractionTransform.PRODUCT
    )
    with pytest.raises(ContractError, match="state"):
        case.engine.apply(fixed, case.inputs.fingerprint, 60, state.fingerprint)
    unrelated = replace(case.fixture.specs[0], cutoff_ns=41)
    with pytest.raises(ContractError, match="cutoff"):
        case.engine.publish_spec(unrelated)


def test_probability_payload_forgery(case: Case) -> None:
    view = case.forecast.probability
    assert view is not None
    tampered = replace(
        view,
        distribution=replace(view.distribution, location=view.distribution.location + 0.01),
    )
    with pytest.raises(ContractError, match="forgery"), case.repo.transaction():
        case.repo.put(tampered)
    assert case.repo.get(NonlinearProbabilityView, view.fingerprint) == view


def test_known_stability_arithmetic(case: Case, monkeypatch: pytest.MonkeyPatch) -> None:
    model = case.fixture.models[0]
    width = len(model.columns)
    left = replace(model, coefficients=(2.0,) * width, scales=(2.0,) * width)
    right = replace(model, coefficients=(-4.0,) * width, scales=(2.0,) * width)
    A = TypeVar("A", bound=Artifact)
    original = case.repo.resolve
    alternatives = {m.fingerprint: m for m in (left, right)}

    def resolve(cls: type[A], identity: str) -> A:
        if cls is NonlinearModelArtifact and identity in alternatives:
            value = alternatives[identity]
            assert isinstance(value, cls)
            return value
        return original(cls, identity)

    monkeypatch.setattr(case.repo, "resolve", resolve)
    result = stability_for(case.repo, tuple(alternatives), 100)
    assert result.coefficient_sign_consistency == (0.5,) * width
    assert result.coefficient_magnitude_drift == (1.0,) * width
    assert not result.split_recurrence


def test_tree_stability_split_recurrence(case: Case) -> None:
    spec = replace(case.fixture.specs[2], seed=13)
    definition = next(
        d for d in spec.interaction_set.definitions if d.interaction_id == "piecewise"
    )
    state = case.engine.fit_transform(spec, definition, case.fixture.train_ids, 40, 40, 40)
    matrix = case.engine.matrix(spec, case.fixture.train_ids, (state.fingerprint,), 40)
    model = case.engine.fit(spec, matrix.fingerprint, 40, 40, 40)
    first = case.fixture.models[2]
    result = case.engine.stability((first.fingerprint, model.fingerprint), 100)
    assert result.split_recurrence == tuple(
        float(any(n.feature_id == c for n in first.nodes)) for c in first.columns
    )
    assert not result.coefficient_sign_consistency
    assert case.repo.get(InteractionStability, result.fingerprint) == result
    with pytest.raises(ContractError, match="compatible"):
        case.engine.stability((case.fixture.models[0].fingerprint, model.fingerprint), 100)


def test_prediction_input_grid_and_feature_revision(case: Case) -> None:
    with pytest.raises(ContractError, match="unique"):
        replace(case.inputs, scalars=(case.inputs.scalars[0],) * 2)
    incomplete = replace(case.inputs, scalars=case.inputs.scalars[:-1])
    with case.repo.transaction():
        case.repo.put(incomplete)
    with pytest.raises(ContractError, match="feature/target"):
        case.engine.predict(case.forecast.model_id, incomplete.fingerprint, 60)
    scalar = case.inputs.scalars[0]
    false = replace(scalar, available_ns=max(0, scalar.available_ns - 1))
    with pytest.raises(ContractError, match="forgery"), case.repo.transaction():
        case.repo.put(false)


def test_propagated_missing_value_is_none_and_fallback_explicit(case: Case) -> None:
    from afre.cross_sectional.engine import CrossSectionEngine
    from afre.cross_sectional.external import ExternalSignal
    from afre.cross_sectional.schema import SignalQuality

    scalar = next(
        s for s in case.inputs.scalars if s.definition.kind is ScalarSourceKind.EXTERNAL_SIGNAL
    )
    source = case.repo.get(ExternalSignal, scalar.source_id)
    absent = replace(source, value=None, quality=SignalQuality.MISSING)
    CrossSectionEngine(case.repo).publish_external(absent)
    missing = case.engine.scalar(absent.fingerprint, scalar.origin)
    packet = case.engine.input(
        case.inputs.sample_id,
        tuple(
            missing.fingerprint if s == scalar else s.fingerprint for s in case.inputs.scalars
        ),
    )
    definition = next(
        d
        for d in case.fixture.specs[0].interaction_set.definitions
        if scalar.definition in d.inputs
    )
    propagate = replace(definition, missing_policy=InteractionMissingPolicy.PROPAGATE_MISSING)
    assert case.engine.apply(propagate, packet.fingerprint, 60).value is None
    fallback = replace(
        propagate, missing_policy=InteractionMissingPolicy.DECLARED_FALLBACK, fallback_value=7.0
    )
    value = case.engine.apply(fallback, packet.fingerprint, 60)
    assert value.value == 7.0 and value.used_fallback


def test_matched_baseline_rejects_different_origin_and_cutoff(case: Case) -> None:
    baselines = tuple(
        (case.repo.get(NonlinearForecast, i).sample_id, i)
        for i in case.fixture.test_forecast_ids
    )
    with pytest.raises(ContractError, match="grid"):
        case.engine.evaluate(case.fixture.forecast_ids[0], 100, 100, baselines)
    with pytest.raises(ContractError, match="known truth|unavailable"):
        case.engine.evaluate(case.fixture.forecast_ids[0], 60, 60)
    with pytest.raises(ContractError, match="duplicates"):
        case.engine.evaluate((case.forecast.fingerprint,) * 2, 100, 100)


def test_standalone_training_row_truth_forgery(case: Case) -> None:
    from afre.nonlinear import InteractionMatrix

    matrix = case.repo.get(InteractionMatrix, case.fixture.models[0].matrix_id)
    row = matrix.rows[0]
    with pytest.raises(ContractError, match="forgery"), case.repo.transaction():
        case.repo.put(replace(row, response=row.response + 1.0))


def test_audit_all_completed_root_families(case: Case) -> None:
    evaluated = case.engine.evaluate(case.fixture.forecast_ids[0], 100, 100)
    assessment = case.engine.assess_calibration(case.forecast.fingerprint, (), 100)
    for root in (
        case.fixture.models[0].fingerprint,
        case.inputs.fingerprint,
        evaluated.fingerprint,
        assessment.fingerprint,
    ):
        audit = case.engine.audit_lineage(root)
        assert root in audit.node_ids
    assert case.repo.get(NonlinearEvaluation, evaluated.fingerprint) == evaluated
