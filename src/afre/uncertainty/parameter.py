"""Fit immutable TRAIN-only OLS covariance separately from feature-only application."""

from typing import TYPE_CHECKING

from afre.nonlinear.artifacts import (
    InteractionMatrix,
    NonlinearForecast,
    NonlinearModelArtifact,
)
from afre.nonlinear.definitions import NonlinearModelSpec
from afre.nonlinear.schema import NonlinearFamily
from afre.schema import ContractError, require
from afre.sequence.artifacts import (
    SequenceDataset,
    SequenceForecast,
    SequenceModelArtifact,
    SequenceSnapshot,
    SequenceTransformArtifact,
)
from afre.sequence.definitions import SequenceModelSpec
from afre.sequence.models import temporal_features
from afre.statistical_models.artifacts import (
    DesignMatrix,
    FittedModelArtifact,
    ModelFitInputs,
    PointForecast,
)
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.linear_algebra import dot, finite
from afre.statistical_models.schema import InterceptPolicy, ModelFamily
from afre.uncertainty.artifacts import ParameterCovariance
from afre.uncertainty.covariance import inverse_crossproduct
from afre.uncertainty.definitions import ParameterUncertaintySpec
from afre.uncertainty.schema import IdentifiabilityStatus

if TYPE_CHECKING:
    from afre.uncertainty.repository import UncertaintyRepository
    from afre.uncertainty.sources import ForecastSource


def covariance_for(
    repo: "UncertaintyRepository", policy: ParameterUncertaintySpec, computed_ns: int
) -> ParameterCovariance:
    model = repo.get_any(policy.model_id)
    require(
        isinstance(model, (FittedModelArtifact, NonlinearModelArtifact, SequenceModelArtifact)),
        "parameter source model family",
    )
    assert isinstance(
        model, (FittedModelArtifact, NonlinearModelArtifact, SequenceModelArtifact)
    )
    repo._validate_links(model)
    spec: BaselineModelSpec | NonlinearModelSpec | SequenceModelSpec
    intercept = True
    if isinstance(model, FittedModelArtifact):
        spec = repo.resolve(BaselineModelSpec, model.spec_id)
        inputs = repo.resolve(ModelFitInputs, model.fit_inputs_id)
        matrix_id, samples = inputs.matrix_id, inputs.train_sample_ids
        cutoff = inputs.training_cutoff_ns
        intercept = spec.intercept is InterceptPolicy.GLOBAL
        eligible = spec.family in (
            ModelFamily.LINEAR_REGRESSION,
            ModelFamily.CROSS_SECTIONAL_LINEAR,
            ModelFamily.RESIDUAL_LINEAR,
        ) and spec.intercept in (InterceptPolicy.GLOBAL, InterceptPolicy.NONE)
        eligible = eligible and model.l1_penalty == model.l2_penalty == 0
        reason = (
            "unpenalized-fixed-linear-design"
            if eligible
            else "ridge-lasso-constant-or-within-origin-unsupported"
        )
    elif isinstance(model, NonlinearModelArtifact):
        spec = repo.resolve(NonlinearModelSpec, model.spec_id)
        matrix_id, samples, cutoff = model.matrix_id, model.train_sample_ids, model.cutoff_ns
        eligible = (
            model.family
            in (
                NonlinearFamily.LINEAR_ON_INTERACTIONS,
                NonlinearFamily.LINEAR_PLUS_INTERACTIONS,
            )
            and spec.ridge_penalty == 0
        )
        reason = (
            "fixed-nonlinear-columns-linear-readout"
            if eligible
            else "tree-or-ridge-covariance-unsupported"
        )
    else:
        spec = repo.resolve(SequenceModelSpec, model.spec_id)
        matrix_id, samples, cutoff = model.dataset_id, model.train_sample_ids, model.cutoff_ns
        eligible = spec.ridge_penalty == 0
        reason = (
            "fixed-temporal-dynamics-readout-only"
            if eligible
            else "ridge-readout-covariance-unsupported"
        )
    require(computed_ns >= model.available_ns, "covariance before fitted model availability")
    status = IdentifiabilityStatus.INCOMPATIBLE
    covariance: tuple[tuple[float, ...], ...] = ()
    sigma = sse = condition = None
    rank = degrees = 0
    if eligible:
        if isinstance(model, FittedModelArtifact):
            matrix = repo.resolve(DesignMatrix, matrix_id)
            repo._validate_links(matrix)
            x, y = tuple(r.values for r in matrix.rows), tuple(r.response for r in matrix.rows)
            require(
                set(samples) == {r.sample_id for r in matrix.rows},
                "covariance exact model TRAIN set",
            )
            ready = matrix.transformed_ns
        elif isinstance(model, NonlinearModelArtifact):
            nl_matrix = repo.resolve(InteractionMatrix, matrix_id)
            repo._validate_links(nl_matrix)
            x = tuple(
                tuple(
                    finite((v - c) / s)
                    for v, c, s in zip(r.values, model.centers, model.scales, strict=True)
                )
                for r in nl_matrix.rows
            )
            y, ready = tuple(r.response for r in nl_matrix.rows), nl_matrix.computed_ns
        else:
            dataset = repo.resolve(SequenceDataset, matrix_id)
            repo._validate_links(dataset)
            state = repo.resolve(SequenceTransformArtifact, model.transform_id)
            assert isinstance(spec, SequenceModelSpec)
            x = tuple(
                temporal_features(spec, repo.resolve(SequenceSnapshot, r.snapshot_id), state)[0]
                for r in dataset.rows
            )
            y, ready = tuple(r.response for r in dataset.rows), dataset.computed_ns
        design = tuple((1.0, *r) if intercept else r for r in x)
        b = repo.uncertainty_bounds
        width = len(design[0])
        require(
            len(x) <= b.samples
            and width <= b.dimensions
            and len(x) * width * width <= b.work_cells
            and ready <= computed_ns,
            "covariance TRAIN work/dimension/availability bound",
        )
        if len(x) < policy.minimum_samples or len(x) <= width:
            status, reason = (
                IdentifiabilityStatus.INSUFFICIENT_DATA,
                "positive-OLS-residual-degrees-required",
            )
        else:
            try:
                inverse, condition = inverse_crossproduct(
                    design, policy.tolerance, policy.condition_limit
                )
            except ContractError as error:
                if "rank-deficient" not in str(error) and "ill-conditioned" not in str(error):
                    raise
                status, reason, condition = IdentifiabilityStatus.INCOMPATIBLE, str(error), None
            else:
                residuals = tuple(
                    finite(v - model.intercept - dot(r, model.coefficients))
                    for r, v in zip(x, y, strict=True)
                )
                sse = dot(residuals, residuals)
                rank, degrees = width, len(x) - width
                sigma = finite(sse / degrees)
                covariance = tuple(tuple(finite(sigma * v) for v in r) for r in inverse)
                status = IdentifiabilityStatus.PARTIALLY_IDENTIFIED
                reason += ":conditional-on-declared-iid-homoskedastic-correct-model-assumptions"
    return ParameterCovariance(
        policy.fingerprint,
        model.fingerprint,
        spec.target.fingerprint,
        spec.target.horizon.fingerprint,
        spec.fold_id,
        matrix_id,
        samples,
        status,
        reason,
        covariance,
        sigma,
        sse,
        degrees,
        rank,
        intercept,
        condition,
        cutoff,
        computed_ns,
        computed_ns,
    )


def prediction_design(
    repo: "UncertaintyRepository", source: "ForecastSource", estimator: ParameterCovariance
) -> tuple[float, ...]:
    from afre.calibration.artifacts import CalibratedForecast
    from afre.feature_store.materialization import PointInTimeJoinResult
    from afre.probabilistic.artifacts import ProbabilisticForecast
    from afre.statistical_models.design_matrix import feature_values, preprocessing_states

    forecast = source.artifact
    if isinstance(forecast, CalibratedForecast):
        forecast = repo.resolve(ProbabilisticForecast, forecast.raw_forecast_id)
    if isinstance(forecast, ProbabilisticForecast):
        forecast = repo.resolve(PointForecast, forecast.point_forecast_id)
    require(
        isinstance(forecast, (PointForecast, NonlinearForecast, SequenceForecast)),
        "conditioned/gated parameter covariance is not supported",
    )
    assert isinstance(forecast, (PointForecast, NonlinearForecast, SequenceForecast))
    model_id = (
        forecast.model_artifact_id if isinstance(forecast, PointForecast) else forecast.model_id
    )
    require(
        model_id == estimator.model_id
        and estimator.target_id == source.target.fingerprint
        and estimator.fold_id == source.fold_id
        and estimator.available_ns <= source.origin.availability_cutoff_ns,
        "parameter covariance exact model/target/fold/availability",
    )
    if isinstance(forecast, PointForecast):
        model = repo.resolve(FittedModelArtifact, model_id)
        spec = repo.resolve(BaselineModelSpec, model.spec_id)
        join = repo.resolve(PointInTimeJoinResult, forecast.input.join_id)
        values, _ = feature_values(
            join,
            model.feature_ids,
            preprocessing_states(repo, spec, False),
            source.origin.availability_cutoff_ns,
        )
        require(values is not None, "parameter prediction missing feature design")
        assert values is not None
    else:
        values = (
            forecast.column_values
            if isinstance(forecast, NonlinearForecast)
            else forecast.aggregates
        )
    return (1.0, *values) if estimator.intercept_included else values
