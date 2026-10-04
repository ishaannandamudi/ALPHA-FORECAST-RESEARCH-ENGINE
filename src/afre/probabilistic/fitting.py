"""Exact frozen AFRE-5 TRAIN evidence, never held-out residuals."""

from typing import TYPE_CHECKING

from afre.probabilistic.artifacts import (
    ProbabilisticFitDiagnostics,
    ProbabilisticFitInputs,
    ProbabilisticModelArtifact,
    TrainingDistribution,
    TrainingObservation,
    TrainingObservations,
)
from afre.probabilistic.definitions import ProbabilisticModelSpec
from afre.probabilistic.scale import estimate_scale, moments
from afre.probabilistic.schema import (
    APPROXIMATION_VERSION,
    IMPLEMENTATION_VERSION,
    DistributionFamily,
    ObservationPolicy,
    ResidualCentering,
)
from afre.schema import require
from afre.statistical_models.artifacts import (
    DesignMatrix,
    FittedModelArtifact,
    ModelFitInputs,
    ModelFitRun,
)
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.linear_algebra import dot, finite
from afre.statistical_models.schema import ModelFamily

if TYPE_CHECKING:
    from afre.probabilistic.repository import ProbabilisticRepository


def point_context(
    repo: "ProbabilisticRepository", spec: ProbabilisticModelSpec, validate: bool
) -> tuple[FittedModelArtifact, ModelFitInputs]:
    require(
        spec.implementation_version == IMPLEMENTATION_VERSION
        and spec.approximation_version == APPROXIMATION_VERSION
        and spec.quantiles.implementation_version == "type7-v1",
        "unknown probability implementation/approximation",
    )
    model = repo.resolve(FittedModelArtifact, spec.point_model_id)
    inputs = repo.resolve(ModelFitInputs, model.fit_inputs_id)
    base_spec = repo.resolve(BaselineModelSpec, model.spec_id)
    rows = repo._connection.execute(
        "SELECT fingerprint FROM m_fits WHERE artifact_id=?", (model.fingerprint,)
    ).fetchall()
    require(
        len(rows) == 1 and model.diagnostics.converged,
        "uncertainty requires one completed converged point fit",
    )
    run = repo.resolve(ModelFitRun, rows[0][0])
    require(
        run.inputs == inputs
        and run.artifact_id == model.fingerprint
        and run.diagnostics_id == model.diagnostics.fingerprint,
        "point fit lineage mismatch",
    )
    require(
        base_spec.target == spec.target
        and inputs.fold_id == spec.fold_id
        and inputs.training_cutoff_ns == spec.training_cutoff_ns,
        "probability point-model target/fold/cutoff mismatch",
    )
    require(
        spec.observation_policy is not ObservationPolicy.TRAIN_TARGETS
        or base_spec.family is ModelFamily.UNCONDITIONAL_MEAN,
        "unconditional distributions require an exact TRAIN mean scaffold",
    )
    if validate:
        repo._validate_links(run)
    return model, inputs


def observations_for(
    repo: "ProbabilisticRepository", spec: ProbabilisticModelSpec
) -> TrainingObservations:
    model, inputs = point_context(repo, spec, True)
    matrix = repo.resolve(DesignMatrix, inputs.matrix_id)
    require(
        len(matrix.rows) <= repo.probabilistic_bounds.observations,
        "TRAIN observation count bound",
    )
    repo._validate_links(matrix)
    rows = []
    for row in matrix.rows:
        prediction = (
            finite(model.intercept + dot(row.values, model.coefficients))
            if spec.observation_policy is ObservationPolicy.POINT_MODEL_RESIDUALS
            else None
        )
        value = row.response if prediction is None else finite(row.response - prediction)
        rows.append(
            TrainingObservation(
                row.sample_id,
                row.target_id,
                row.origin.timestamp_ns,
                row.origin.instrument.fingerprint,
                row.response,
                prediction,
                value,
                max(row.data_available_ns, model.available_ns),
            )
        )
    return TrainingObservations(spec.fingerprint, matrix.fingerprint, tuple(rows))


def distribution_for(
    spec: ProbabilisticModelSpec, observations: TrainingObservations, available_ns: int
) -> TrainingDistribution:
    raw = tuple(row.value for row in observations.rows)
    raw_mean = moments(raw)[0]
    shift = raw_mean if spec.residual_centering is ResidualCentering.CENTER_MEAN else 0.0
    values = tuple(sorted(finite(value - shift) for value in raw))
    mean, med, std, mad = moments(values)
    scale = estimate_scale(
        values, spec.scale, spec.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
    )
    diagnostics = ProbabilisticFitDiagnostics(
        len(values), raw_mean, shift, mean, med, std, mad, scale, min(raw) == max(raw)
    )
    return TrainingDistribution(
        spec.fingerprint,
        observations.fingerprint,
        tuple(r.sample_id for r in observations.rows),
        values,
        diagnostics,
        available_ns,
    )


def artifact_for(
    spec: ProbabilisticModelSpec,
    inputs: ProbabilisticFitInputs,
    distribution: TrainingDistribution,
) -> ProbabilisticModelArtifact:
    return ProbabilisticModelArtifact(
        spec.fingerprint,
        inputs.fingerprint,
        distribution.fingerprint,
        spec.family,
        distribution.diagnostics.distribution_mean
        if spec.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
        else 0.0,
        distribution.diagnostics.estimated_scale,
        distribution.diagnostics.fingerprint,
        spec.approximation_version,
        inputs.available_ns,
    )
