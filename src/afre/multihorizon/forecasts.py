"""Target-free bundle assembly and explicit raw/calibrated surfaces."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibratedForecast
from afre.feature_store.materialization import PointInTimeJoinResult
from afre.forecast import ForecastOrigin
from afre.horizons import ForecastHorizon
from afre.multihorizon.artifacts import (
    CovarianceArtifact,
    HorizonForecastEntry,
    MultiHorizonFitRun,
    MultiHorizonForecast,
    SharedParameters,
    SharedPointForecast,
    SurfaceRow,
    SurfaceValue,
)
from afre.multihorizon.definitions import MultiHorizonModelSpec
from afre.multihorizon.horizon_sets import HorizonSet
from afre.multihorizon.schema import (
    Architecture,
    Completeness,
    ComponentState,
    DependenceMethod,
)
from afre.probabilistic.artifacts import (
    ProbabilisticForecast,
    QuantileValue,
    ThresholdProbability,
)
from afre.schema import require
from afre.statistical_models.artifacts import PointForecast
from afre.statistical_models.design_matrix import feature_values
from afre.statistical_models.linear_algebra import dot, finite

if TYPE_CHECKING:
    from afre.multihorizon.repository import MultiHorizonRepository


def shared_point_for(
    repo: "MultiHorizonRepository",
    run: MultiHorizonFitRun,
    scaffold: PointForecast,
    computed_ns: int,
) -> SharedPointForecast:
    spec = repo.resolve(MultiHorizonModelSpec, run.spec_id)
    require(spec.architecture is Architecture.SHARED_LINEAR_BACKBONE, "no shared point layer")
    state = repo.resolve(SharedParameters, run.shared_parameters_id or "")
    index = tuple(b.target_definition_id for b in spec.bindings).index(
        scaffold.target_definition_id
    )
    require(
        scaffold.model_artifact_id == spec.bindings[index].point_model_id
        and scaffold.historical_admissible
        and state.available_ns <= scaffold.input.origin.availability_cutoff_ns,
        "shared model unavailable or wrong horizon scaffold",
    )
    require(
        computed_ns >= scaffold.available_ns,
        "shared computation precedes scaffold availability",
    )
    repo._validate_links(scaffold)
    join = repo.resolve(PointInTimeJoinResult, scaffold.input.join_id)
    values, _ = feature_values(
        join, state.feature_ids, (), scaffold.input.origin.availability_cutoff_ns
    )
    require(values is not None, "shared features unavailable")
    assert values is not None
    return SharedPointForecast(
        run.fingerprint,
        state.fingerprint,
        scaffold.target_definition_id,
        scaffold.fingerprint,
        scaffold.input,
        finite(dot(values, state.coefficients) + state.intercepts[index]),
        computed_ns,
        max(scaffold.available_ns, computed_ns),
    )


def bundle_for(
    repo: "MultiHorizonRepository",
    run: MultiHorizonFitRun,
    origin: ForecastOrigin,
    entries: tuple[HorizonForecastEntry, ...],
    computed_ns: int,
    covariance_id: str | None = None,
) -> MultiHorizonForecast:
    spec = repo.resolve(MultiHorizonModelSpec, run.spec_id)
    lookup = {e.target_definition_id: e for e in entries}
    require(
        len(lookup) == len(entries)
        and set(lookup) == {b.target_definition_id for b in spec.bindings},
        "bundle must retain every declared horizon",
    )
    require(computed_ns >= origin.timestamp_ns, "bundle computation before origin")
    ordered = tuple(lookup[b.target_definition_id] for b in spec.bindings)
    included, availability = 0, [computed_ns]
    for binding, entry in zip(spec.bindings, ordered, strict=True):
        if entry.state is not ComponentState.AVAILABLE:
            continue
        included += 1
        require(
            run.available_ns <= origin.availability_cutoff_ns,
            "multi-horizon fit unavailable at origin",
        )
        if spec.architecture is Architecture.SHARED_LINEAR_BACKBONE:
            point: PointForecast | SharedPointForecast = repo.resolve(
                SharedPointForecast, entry.point_forecast_id or ""
            )
            assert isinstance(point, SharedPointForecast)
            require(point.fit_run_id == run.fingerprint, "shared point fit mismatch")
        else:
            point = repo.resolve(PointForecast, entry.point_forecast_id or "")
            require(
                point.model_artifact_id == binding.point_model_id
                and point.historical_admissible,
                "bundle point model mismatch or retrospective",
            )
        require(
            point.input.origin == origin
            and point.target_definition_id == binding.target_definition_id,
            "bundle full origin/security/target mismatch",
        )
        require(
            (entry.probability_forecast_id is None) == (binding.probability_model_id is None)
            and (entry.calibrated_forecast_id is None)
            == (binding.calibration_state_id is None),
            "bundle required layer missing",
        )
        repo._validate_links(point)
        availability.append(point.available_ns)
        if entry.probability_forecast_id is not None:
            raw = repo.resolve(ProbabilisticForecast, entry.probability_forecast_id)
            require(
                raw.model_artifact_id == binding.probability_model_id
                and raw.point_forecast_id == point.fingerprint
                and raw.input == point.input
                and raw.target_definition_id == binding.target_definition_id
                and raw.historical_admissible,
                "bundle probability horizon/model mismatch",
            )
            repo._validate_links(raw)
            availability.append(raw.available_ns)
        if entry.calibrated_forecast_id is not None:
            calibrated = repo.resolve(CalibratedForecast, entry.calibrated_forecast_id)
            require(
                calibrated.state_id == binding.calibration_state_id
                and calibrated.raw_forecast_id == entry.probability_forecast_id
                and calibrated.input == point.input
                and calibrated.target_definition_id == binding.target_definition_id,
                "bundle calibrated horizon/state mismatch",
            )
            repo._validate_links(calibrated)
            availability.append(calibrated.available_ns)
    if covariance_id is not None:
        covariance = repo.resolve(CovarianceArtifact, covariance_id)
        require(
            covariance.fit_run_id == run.fingerprint
            and covariance.available_ns <= origin.availability_cutoff_ns,
            "dependence unavailable or mismatched at origin",
        )
        availability.append(covariance.available_ns)
    require(
        computed_ns >= max(availability),
        "bundle computation precedes included artifact availability",
    )
    completeness = (
        Completeness.COMPLETE
        if included == len(ordered)
        else (Completeness.PARTIAL if included else Completeness.UNAVAILABLE)
    )
    return MultiHorizonForecast(
        run.fingerprint,
        spec.horizon_set.fingerprint,
        spec.architecture,
        origin,
        ordered,
        completeness,
        DependenceMethod.EMPIRICAL_RESIDUAL_COVARIANCE
        if covariance_id
        else DependenceMethod.NONE,
        covariance_id,
        computed_ns,
        max(availability),
        bool(included),
    )


def forecast_for_horizon(
    bundle: MultiHorizonForecast, horizons: HorizonSet, horizon: ForecastHorizon
) -> HorizonForecastEntry:
    require(bundle.horizon_set_id == horizons.fingerprint, "query horizon set mismatch")
    target = horizons.target_for(horizon)
    return next(e for e in bundle.entries if e.target_definition_id == target.fingerprint)


def surfaces(
    repo: "MultiHorizonRepository", bundle: MultiHorizonForecast, calibrated: bool = False
) -> tuple[tuple[SurfaceValue, ...], tuple[SurfaceValue, ...], tuple[SurfaceRow, ...]]:
    expectations, medians, rows = [], [], []
    for entry in bundle.entries:
        state = entry.state
        expectation, median = None, None
        quantiles: tuple[QuantileValue, ...] = ()
        probabilities: tuple[ThresholdProbability, ...] = ()
        if state is ComponentState.AVAILABLE:
            if entry.probability_forecast_id is None:
                state = ComponentState.UNSUPPORTED
            else:
                raw = repo.resolve(ProbabilisticForecast, entry.probability_forecast_id)
                expectation, median = raw.expected_value, raw.median_value
                quantiles, probabilities = raw.quantiles, raw.threshold_probabilities
                if calibrated:
                    if entry.calibrated_forecast_id is None:
                        state, expectation, median = ComponentState.MISSING, None, None
                        quantiles, probabilities = (), ()
                    else:
                        adjusted = repo.resolve(
                            CalibratedForecast, entry.calibrated_forecast_id
                        )
                        quantiles, probabilities = adjusted.quantiles, adjusted.probabilities
                        median = next(q.value for q in quantiles if q.level == 0.5)
                        if not adjusted.full_distribution_preserved:
                            expectation = None
        expectations.append(
            SurfaceValue(
                entry.target_definition_id,
                state
                if expectation is not None or state is not ComponentState.AVAILABLE
                else ComponentState.UNSUPPORTED,
                expectation,
            )
        )
        medians.append(SurfaceValue(entry.target_definition_id, state, median))
        rows.append(SurfaceRow(entry.target_definition_id, state, quantiles, probabilities))
    return tuple(expectations), tuple(medians), tuple(rows)
