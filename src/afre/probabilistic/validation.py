"""Exact TRAIN uncertainty and target-free forecast replay reject semantic forgery."""

from typing import TYPE_CHECKING

from afre.probabilistic.artifacts import (
    ProbabilisticComparison,
    ProbabilisticEvaluation,
    ProbabilisticFitInputs,
    ProbabilisticFitRun,
    ProbabilisticForecast,
    ProbabilisticLineageAudit,
    ProbabilisticModelArtifact,
    TrainingDistribution,
    TrainingObservations,
)
from afre.probabilistic.definitions import (
    ProbabilisticEvaluationProtocol,
    ProbabilisticModelSpec,
    QuantileDefinition,
)
from afre.probabilistic.evaluation import comparison_for, evaluate_forecasts
from afre.probabilistic.fitting import (
    artifact_for,
    distribution_for,
    observations_for,
    point_context,
)
from afre.probabilistic.forecast import forecast_for
from afre.research_datasets.splits import TestEvaluation
from afre.schema import Artifact, require
from afre.statistical_models.artifacts import PointForecast

if TYPE_CHECKING:
    from afre.probabilistic.repository import ProbabilisticRepository


def validate_probability_links(repo: "ProbabilisticRepository", value: Artifact) -> None:
    if isinstance(value, ProbabilisticModelSpec):
        point_context(repo, value, True)
    elif isinstance(value, QuantileDefinition):
        require(
            value.implementation_version == "type7-v1", "unknown quantile convention version"
        )
    elif isinstance(value, ProbabilisticEvaluationProtocol):
        require(
            value.implementation_version == "proper-scores-v1",
            "unknown scoring protocol version",
        )
    elif isinstance(value, TrainingObservations):
        spec = repo.resolve(ProbabilisticModelSpec, value.spec_id)
        require(
            value == observations_for(repo, spec), "TRAIN probability observation contamination"
        )
    elif isinstance(value, ProbabilisticFitInputs):
        spec = repo.resolve(ProbabilisticModelSpec, value.spec_id)
        model, base_inputs = point_context(repo, spec, True)
        observations = repo.resolve(TrainingObservations, value.observations_id)
        repo._validate_links(observations)
        require(
            (
                value.spec_id,
                value.point_model_id,
                value.point_fit_inputs_id,
                value.matrix_id,
                value.dataset_id,
                value.split_id,
                value.fold_id,
                value.target_definition_id,
                value.train_sample_ids,
                value.preprocessing_state_ids,
                value.training_cutoff_ns,
            )
            == (
                spec.fingerprint,
                model.fingerprint,
                base_inputs.fingerprint,
                base_inputs.matrix_id,
                base_inputs.dataset_id,
                base_inputs.split_id,
                base_inputs.fold_id,
                spec.target.fingerprint,
                tuple(r.sample_id for r in observations.rows),
                base_inputs.preprocessing_state_ids,
                base_inputs.training_cutoff_ns,
            ),
            "probability fit-input lineage mismatch",
        )
        require(
            value.fit_started_ns >= model.available_ns
            and value.available_ns >= max(r.data_available_ns for r in observations.rows),
            "probability fit before point/input availability",
        )
    elif isinstance(value, TrainingDistribution):
        spec = repo.resolve(ProbabilisticModelSpec, value.spec_id)
        observations = repo.resolve(TrainingObservations, value.observations_id)
        repo._validate_links(observations)
        require(
            value.available_ns >= max(r.data_available_ns for r in observations.rows),
            "distribution before TRAIN observation availability",
        )
        require(
            value == distribution_for(spec, observations, value.available_ns),
            "probability distribution/scale replay mismatch",
        )
    elif isinstance(value, ProbabilisticModelArtifact):
        inputs = repo.resolve(ProbabilisticFitInputs, value.fit_inputs_id)
        repo._validate_links(inputs)
        state = repo.resolve(TrainingDistribution, value.distribution_id)
        repo._validate_links(state)
        spec = repo.resolve(ProbabilisticModelSpec, inputs.spec_id)
        require(
            state.spec_id == spec.fingerprint
            and state.observations_id == inputs.observations_id
            and state.available_ns == inputs.available_ns
            and value == artifact_for(spec, inputs, state),
            "probability artifact replay mismatch",
        )
    elif isinstance(value, ProbabilisticFitRun):
        artifact = repo.resolve(ProbabilisticModelArtifact, value.artifact_id)
        repo._validate_links(artifact)
        state = repo.resolve(TrainingDistribution, artifact.distribution_id)
        require(
            value.inputs == repo.resolve(ProbabilisticFitInputs, artifact.fit_inputs_id)
            and value.distribution_id == state.fingerprint
            and value.diagnostics_id == artifact.diagnostics_id
            and repo.get_any(value.diagnostics_id) == state.diagnostics,
            "probability run/artifact mismatch",
        )
    elif isinstance(value, ProbabilisticForecast):
        artifact = repo.resolve(ProbabilisticModelArtifact, value.model_artifact_id)
        point, replay = forecast_for(repo, artifact, value.input, value.computed_ns)
        require(
            point == repo.resolve(PointForecast, value.point_forecast_id) and value == replay,
            "probabilistic forecast replay mismatch",
        )
    elif isinstance(value, ProbabilisticEvaluation):
        seal = (
            repo.resolve(TestEvaluation, value.test_evaluation_id)
            if value.test_evaluation_id
            else None
        )
        require(
            value
            == evaluate_forecasts(
                repo,
                value.forecast_ids,
                value.protocol,
                value.evaluation_cutoff_ns,
                value.available_ns,
                seal,
            ),
            "probabilistic evaluation replay mismatch",
        )
    elif isinstance(value, ProbabilisticComparison):
        require(
            value
            == comparison_for(
                repo, value.candidate_evaluation_id, value.reference_evaluation_id
            ),
            "probability comparison replay mismatch",
        )
    elif isinstance(value, ProbabilisticLineageAudit):
        from afre.probabilistic.lineage import lineage_audit

        require(
            value == lineage_audit(repo, value.root_id), "probability audit evidence mismatch"
        )
