"""Exact origin/layer mappings, explicit missingness and target-free application."""

from dataclasses import replace

import pytest

from afre.calibration import (
    CalibrationEngine,
    CalibrationMethod,
    CalibrationObservationSet,
    CalibrationSpec,
    CalibrationState,
)
from afre.multihorizon import (
    Completeness,
    ComponentState,
    HorizonForecastEntry,
    SharedParameters,
    forecast_for_horizon,
    surfaces,
)
from afre.probabilistic import (
    DistributionFamily,
    ProbabilisticEngine,
    ProbabilisticModelArtifact,
    ProbabilisticModelSpec,
    ThresholdDefinition,
    TrainingObservations,
)
from afre.schema import ContractError
from afre.statistical_models import DesignMatrix, ModelEngine
from afre.statistical_models.artifacts import PointForecast
from afre.target_engine.models import TargetVintage
from examples.multihorizon_demo import backbone_spec
from tests.multihorizon.conftest import Case


def test_exact_vectors_and_query(case: Case) -> None:
    bundle = case.fixture.bundles[0]
    expected, medians, surface = surfaces(case.repo, bundle)
    calibrated = surfaces(case.repo, bundle, True)
    assert calibrated == (expected, medians, surface)
    for h, entry in enumerate(bundle.entries):
        raw = next(
            p
            for p in case.fixture.deployment[h]
            if p.fingerprint == entry.probability_forecast_id
        )
        assert expected[h].value == raw.expected_value
        assert medians[h].value == raw.median_value
        assert surface[h].quantiles == raw.quantiles
        assert surface[h].probabilities == raw.threshold_probabilities
        assert (
            forecast_for_horizon(
                bundle, case.fixture.spec.horizon_set, case.fixture.spec.horizon_set.horizons[h]
            )
            == entry
        )
    # Same GT0 request is a distinct event at each rich target/horizon.
    assert surface[0].target_definition_id != surface[1].target_definition_id
    assert surface[0].probabilities[0].request == surface[1].probabilities[0].request
    with pytest.raises(ContractError):
        forecast_for_horizon(
            bundle,
            replace(
                case.fixture.spec.horizon_set,
                ordering=case.fixture.spec.horizon_set.ordering,
                targets=case.fixture.spec.horizon_set.targets[:1],
            ),
            case.fixture.spec.horizon_set.horizons[0],
        )


@pytest.mark.parametrize("present", [0, 1])
def test_explicit_partial_and_unavailable(case: Case, present: int) -> None:
    original = case.fixture.bundles[0]
    entries = tuple(
        e
        if h < present
        else HorizonForecastEntry(
            e.target_definition_id, ComponentState.MISSING, reason="feature not received"
        )
        for h, e in enumerate(original.entries)
    )
    bundle = case.engine.build_bundle(
        original.fit_run_id, original.origin, tuple(reversed(entries)), 60
    )
    assert bundle.completeness is (
        Completeness.PARTIAL if present else Completeness.UNAVAILABLE
    )
    assert len(bundle.entries) == 2
    expected, median, _ = surfaces(case.repo, bundle)
    assert expected[1].state is median[1].state is ComponentState.MISSING
    evaluation = case.engine.evaluate((bundle.fingerprint,), 75, 75)
    assert evaluation.weighted_mse is None and evaluation.matched_origins == ()
    assert evaluation.horizons[1].missing_count == 1
    with pytest.raises(ContractError):
        case.engine.build_bundle(original.fit_run_id, original.origin, entries[:1], 60)


@pytest.mark.parametrize("change", ["origin", "calibration", "raw", "point", "missing-layer"])
def test_mixed_origin_horizon_layers_rejected(case: Case, change: str) -> None:
    bundle, other = case.fixture.bundles[:2]
    a, b = bundle.entries
    if change == "origin":
        a = other.entries[0]
    elif change == "calibration":
        a = replace(a, calibrated_forecast_id=b.calibrated_forecast_id)
    elif change == "raw":
        a = replace(a, probability_forecast_id=b.probability_forecast_id)
    elif change == "point":
        a = replace(a, point_forecast_id=b.point_forecast_id)
    else:
        a = replace(a, calibrated_forecast_id=None)
    with pytest.raises(ContractError):
        case.engine.build_bundle(bundle.fit_run_id, bundle.origin, (a, b), 60)


def test_actual_bundle_availability(case: Case) -> None:
    bundle = case.fixture.bundles[0]
    later = case.engine.build_bundle(bundle.fit_run_id, bundle.origin, bundle.entries, 110)
    assert later.available_ns == 110 and later.historical_admissible
    assert later.fingerprint != bundle.fingerprint
    with pytest.raises(ContractError):
        case.engine.build_bundle(bundle.fit_run_id, bundle.origin, bundle.entries, 59)
    covariance = case.engine.fit_dependence(bundle.fit_run_id, 40, 61)
    with pytest.raises(ContractError, match="dependence unavailable"):
        case.engine.build_bundle(
            bundle.fit_run_id, bundle.origin, bundle.entries, 61, covariance.fingerprint
        )
    future = case.engine.fit(case.fixture.spec, 61, 61, 61)
    with pytest.raises(ContractError, match="fit unavailable"):
        case.engine.build_bundle(future.fingerprint, bundle.origin, bundle.entries, 61)


def test_point_only_surfaces_and_missing_calibration(case: Case) -> None:
    bundle = case.fixture.bundles[0]
    spec = replace(
        case.fixture.spec,
        bindings=tuple(
            replace(b, calibration_spec_id=None, calibration_state_id=None)
            for b in case.fixture.spec.bindings
        ),
    )
    run = case.engine.fit(spec, 55, 55, 55)
    built = case.engine.build_bundle(
        run.fingerprint,
        bundle.origin,
        tuple(replace(e, calibrated_forecast_id=None) for e in bundle.entries),
        60,
    )
    assert all(v.state is ComponentState.MISSING for v in surfaces(case.repo, built, True)[0])
    shared = case.engine.fit(backbone_spec(case.fixture), 55, 55, 55)
    outputs = tuple(
        case.engine.predict_shared(shared.fingerprint, e.point_forecast_id or "", 60)
        for e in bundle.entries
    )
    built = case.engine.build_bundle(
        shared.fingerprint,
        bundle.origin,
        tuple(
            HorizonForecastEntry(
                p.target_definition_id, ComponentState.AVAILABLE, p.fingerprint
            )
            for p in outputs
        ),
        60,
    )
    assert all(v.state is ComponentState.UNSUPPORTED for v in surfaces(case.repo, built)[0])
    assert case.repo.get(SharedParameters, shared.shared_parameters_id or "").available_ns == 55


def test_sparse_quantiles_no_invented_expectation(case: Case) -> None:
    original = case.fixture.bundles[0]
    b = case.fixture.spec.bindings[0]
    ps = case.repo.get(ProbabilisticModelSpec, b.probability_spec_id or "")
    ps = replace(ps, family=DistributionFamily.QUANTILE_SET, thresholds=ThresholdDefinition(()))
    pe = ProbabilisticEngine(case.repo)
    run = pe.fit_model(ps, 40, 40, 40)
    request = case.repo.get(PointForecast, original.entries[0].point_forecast_id or "").input
    raw = pe.predict(run.artifact_id, request, 60)
    spec = replace(
        case.fixture.spec,
        bindings=(
            replace(
                b,
                probability_spec_id=ps.fingerprint,
                probability_model_id=run.artifact_id,
                calibration_spec_id=None,
                calibration_state_id=None,
            ),
            case.fixture.spec.bindings[1],
        ),
    )
    fitted = case.engine.fit(spec, 55, 55, 55)
    built = case.engine.build_bundle(
        fitted.fingerprint,
        original.origin,
        (
            HorizonForecastEntry(
                raw.target_definition_id,
                ComponentState.AVAILABLE,
                raw.point_forecast_id,
                raw.fingerprint,
            ),
            original.entries[1],
        ),
        60,
    )
    expectation, median, surface = surfaces(case.repo, built)
    assert expectation[0].state is ComponentState.UNSUPPORTED and expectation[0].value is None
    assert median[0].value == raw.median_value and surface[0].probabilities == ()
    assert (
        case.repo.get(ProbabilisticModelArtifact, run.artifact_id).family
        is DistributionFamily.QUANTILE_SET
    )


def test_adjusted_marginals_preserve_no_pdf(case: Case) -> None:
    original = case.fixture.bundles[0]
    b = case.fixture.spec.bindings[0]
    cs = case.repo.get(CalibrationSpec, b.calibration_spec_id or "")
    state = case.repo.get(CalibrationState, b.calibration_state_id or "")
    obs = case.repo.get(CalibrationObservationSet, state.inputs.observations_id)
    engine = CalibrationEngine(case.repo)
    cs = replace(cs, method=CalibrationMethod.QUANTILE_OFFSET)
    fitted = engine.fit(cs, obs.requests, 55, 55, 55)
    adjusted = engine.apply(
        fitted.state_id, original.entries[0].probability_forecast_id or "", 60
    )
    spec = replace(
        case.fixture.spec,
        bindings=(
            replace(
                b, calibration_spec_id=cs.fingerprint, calibration_state_id=fitted.state_id
            ),
            case.fixture.spec.bindings[1],
        ),
    )
    run = case.engine.fit(spec, 55, 55, 55)
    built = case.engine.build_bundle(
        run.fingerprint,
        original.origin,
        (
            replace(original.entries[0], calibrated_forecast_id=adjusted.fingerprint),
            original.entries[1],
        ),
        60,
    )
    expected, medians, _ = surfaces(case.repo, built, True)
    assert expected[0].state is ComponentState.UNSUPPORTED
    assert medians[0].value == next(q.value for q in adjusted.quantiles if q.level == 0.5)


def test_target_free_bundle_and_shared_prediction(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared = case.engine.fit(backbone_spec(case.fixture), 55, 55, 55)
    original_get = case.repo.get

    def guarded(cls: type[object], identity: str) -> object:
        assert cls not in (
            TargetVintage,
            DesignMatrix,
            TrainingObservations,
            CalibrationObservationSet,
        )
        return original_get(cls, identity)  # type: ignore[type-var]

    monkeypatch.setattr(case.repo, "get", guarded)
    bundle = case.fixture.bundles[0]
    assert (
        case.engine.build_bundle(bundle.fit_run_id, bundle.origin, bundle.entries, 60) == bundle
    )
    assert (
        case.engine.predict_shared(
            shared.fingerprint, bundle.entries[0].point_forecast_id or "", 60
        ).available_ns
        == 60
    )


def test_no_naive_return_or_variance_scaling(case: Case) -> None:
    bundle = case.fixture.bundles[0]
    audit = case.engine.consistency_audit(bundle.fingerprint)
    assert (
        audit.same_family_units and audit.compatible_adjustment and audit.nested_elapsed_windows
    )
    assert "nested-simple-returns-not-additive" in audit.checks
    assert "no-variance-horizon-scaling" in audit.checks
    from afre.probabilistic import ProbabilisticForecast

    raw = tuple(
        case.repo.get(ProbabilisticForecast, e.probability_forecast_id or "")
        for e in bundle.entries
    )
    assert raw[1].conditional_variance != pytest.approx(
        3 * (raw[0].conditional_variance or 0.0), rel=1e-6
    )
    assert audit.expectation_differences[0] == pytest.approx(
        (raw[1].expected_value or 0.0) - (raw[0].expected_value or 0.0)
    )


def test_composition_cannot_backdate_physical_computation(case: Case) -> None:
    original = case.fixture.bundles[0]
    point = case.repo.get(PointForecast, original.entries[0].point_forecast_id or "")
    late = ModelEngine(case.repo).predict(point.model_artifact_id, point.input, 110)
    spec = replace(
        case.fixture.spec,
        bindings=tuple(
            replace(
                b,
                probability_spec_id=None,
                probability_model_id=None,
                calibration_spec_id=None,
                calibration_state_id=None,
            )
            for b in case.fixture.spec.bindings
        ),
    )
    run = case.engine.fit(spec, 55, 55, 55)
    entries = (
        HorizonForecastEntry(
            late.target_definition_id, ComponentState.AVAILABLE, late.fingerprint
        ),
        replace(original.entries[1], probability_forecast_id=None, calibrated_forecast_id=None),
    )
    with pytest.raises(ContractError, match="computation precedes"):
        case.engine.build_bundle(run.fingerprint, original.origin, entries, 60)
    assert (
        case.engine.build_bundle(run.fingerprint, original.origin, entries, 110).available_ns
        == 110
    )
    shared = case.engine.fit(backbone_spec(case.fixture), 55, 55, 55)
    with pytest.raises(ContractError, match="computation precedes"):
        case.engine.predict_shared(shared.fingerprint, late.fingerprint, 60)
    assert (
        case.engine.predict_shared(shared.fingerprint, late.fingerprint, 110).available_ns
        == 110
    )


@pytest.mark.parametrize(
    "annualization, compatible", [(None, False), (52.0, False), (252.0, True)]
)
def test_annualized_volatility_units_are_explicit(
    case: Case, annualization: float | None, compatible: bool
) -> None:
    from afre.multihorizon.consistency import compatible_units
    from afre.target_engine.definitions import TargetPathPolicy
    from afre.target_engine.schema import TargetAggregation
    from afre.targets import TargetType

    targets = tuple(
        replace(
            t,
            target_type=TargetType.REALIZED_VOLATILITY,
            aggregation=TargetAggregation.VOLATILITY,
            path=TargetPathPolicy(1, annualization_factor=252.0 if h == 0 else annualization),
        )
        for h, t in enumerate(case.fixture.spec.horizon_set.targets)
    )
    assert compatible_units(targets) is compatible
