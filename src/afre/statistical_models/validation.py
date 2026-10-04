"""Frozen matrix/solver/forecast/evaluation replay and bounded lineage proofs."""

from typing import TYPE_CHECKING

from afre.feature_store.materialization import PointInTimeJoinResult
from afre.research_datasets.manifests import ResearchDatasetManifest
from afre.research_datasets.samples import ResearchSample, ResearchSelection
from afre.research_datasets.splits import FoldDefinition, TestEvaluation
from afre.research_datasets.validation import audit_edges
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import (
    BaselineComparison,
    DesignMatrix,
    FittedModelArtifact,
    ModelFitInputs,
    ModelFitRun,
    ModelLineageAudit,
    PointEvaluation,
    PointForecast,
    PredictionInput,
)
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.design_matrix import (
    build_matrix,
    model_context,
    preprocessing_states,
)
from afre.statistical_models.evaluation import comparison_for, evaluate_forecasts
from afre.statistical_models.fitting import fit_values
from afre.statistical_models.lineage import upstream_edges
from afre.statistical_models.prediction import forecast_for
from afre.statistical_models.schema import IMPLEMENTATION_VERSION, SOLVER_VERSION

if TYPE_CHECKING:
    from afre.statistical_models.repository import ModelRepository


def fitted_artifact(
    repo: "ModelRepository",
    spec: BaselineModelSpec,
    matrix: DesignMatrix,
    inputs: ModelFitInputs,
) -> FittedModelArtifact:
    result = fit_values(spec, matrix, repo.model_bounds)
    return FittedModelArtifact(
        spec.fingerprint,
        spec.foundation_spec.fingerprint,
        inputs.fingerprint,
        matrix.feature_ids,
        result.coefficients,
        result.intercept,
        result.reference_value,
        spec.l1_penalty,
        spec.l2_penalty,
        spec.regularize_intercept,
        spec.solver,
        spec.solver_version,
        result.diagnostics,
        inputs.model_available_ns,
    )


def validate_model_links(repo: "ModelRepository", value: Artifact) -> None:
    if isinstance(value, BaselineModelSpec):
        require(
            value.implementation_version == IMPLEMENTATION_VERSION
            and value.solver_version == SOLVER_VERSION,
            "unsupported model/solver implementation",
        )
        model_context(repo, value)
        preprocessing_states(repo, value, True)
    elif isinstance(value, DesignMatrix):
        spec = repo.resolve(BaselineModelSpec, value.spec_id)
        require(
            value == build_matrix(repo, spec, value.transformed_ns),
            "model TRAIN matrix contamination",
        )
    elif isinstance(value, ModelFitInputs):
        matrix = repo.resolve(DesignMatrix, value.matrix_id)
        repo._validate_links(matrix)
        require(
            (
                value.spec_id,
                value.dataset_id,
                value.split_id,
                value.fold_id,
                value.training_cutoff_ns,
                value.preprocessing_state_ids,
                value.train_sample_ids,
                value.fit_started_ns,
            )
            == (
                matrix.spec_id,
                matrix.dataset_id,
                matrix.split_id,
                matrix.fold_id,
                matrix.training_cutoff_ns,
                matrix.preprocessing_state_ids,
                tuple(r.sample_id for r in matrix.rows),
                matrix.transformed_ns,
            ),
            "model fit inputs/matrix mismatch",
        )
        require(
            value.model_available_ns >= max(r.data_available_ns for r in matrix.rows),
            "model available before TRAIN data/preprocessing",
        )
    elif isinstance(value, FittedModelArtifact):
        inputs = repo.resolve(ModelFitInputs, value.fit_inputs_id)
        repo._validate_links(inputs)
        spec = repo.resolve(BaselineModelSpec, value.spec_id)
        repo._validate_links(spec)
        require(
            spec.foundation_spec == repo.get_any(value.foundation_spec_id),
            "foundation ModelSpec bridge mismatch",
        )
        matrix = repo.resolve(DesignMatrix, inputs.matrix_id)
        require(
            value == fitted_artifact(repo, spec, matrix, inputs),
            "model coefficient/solver replay mismatch",
        )
    elif isinstance(value, ModelFitRun):
        model = repo.resolve(FittedModelArtifact, value.artifact_id)
        repo._validate_links(model)
        require(
            value.inputs == repo.resolve(ModelFitInputs, model.fit_inputs_id)
            and value.diagnostics_id == model.diagnostics.fingerprint
            and repo.get_any(value.diagnostics_id) == model.diagnostics,
            "model run/artifact/diagnostics mismatch",
        )
    elif isinstance(value, PredictionInput):
        join = repo.resolve(PointInTimeJoinResult, value.join_id)
        require(join.row.origin == value.origin, "prediction input origin mismatch")
        if value.sample_id is not None:
            sample = repo.resolve(ResearchSample, value.sample_id)
            require(
                sample.origin == value.origin and sample.join_id == value.join_id,
                "prediction input sample mismatch",
            )
    elif isinstance(value, PointForecast):
        model = repo.resolve(FittedModelArtifact, value.model_artifact_id)
        require(
            value == forecast_for(repo, model, value.input, value.computed_ns),
            "point forecast replay mismatch",
        )
    elif isinstance(value, PointEvaluation):
        seal = (
            repo.resolve(TestEvaluation, value.test_evaluation_id)
            if value.test_evaluation_id
            else None
        )
        require(
            value
            == evaluate_forecasts(
                repo, value.prediction_ids, value.evaluation_cutoff_ns, value.available_ns, seal
            ),
            "point evaluation replay mismatch",
        )
    elif isinstance(value, BaselineComparison):
        require(
            value
            == comparison_for(
                repo, value.candidate_evaluation_id, value.reference_evaluation_id
            ),
            "baseline comparison replay mismatch",
        )
    elif isinstance(value, ModelLineageAudit):
        require(value == lineage_audit(repo, value.root_id), "model audit evidence mismatch")


def model_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, BaselineModelSpec):
        return (
            value.fold_id,
            value.feature_set.fingerprint,
            value.target.fingerprint,
            *value.preprocessing_state_ids,
        )
    if isinstance(value, DesignMatrix):
        return (
            value.spec_id,
            value.dataset_id,
            value.split_id,
            value.fold_id,
            *(r.sample_id for r in value.rows),
            *(r.target_id for r in value.rows),
            *value.preprocessing_state_ids,
        )
    if isinstance(value, ModelFitInputs):
        return (value.spec_id, value.matrix_id, *value.preprocessing_state_ids)
    if isinstance(value, FittedModelArtifact):
        return (
            value.spec_id,
            value.foundation_spec_id,
            value.fit_inputs_id,
            value.diagnostics.fingerprint,
        )
    if isinstance(value, ModelFitRun):
        return (value.inputs.fingerprint, value.artifact_id, value.diagnostics_id)
    if isinstance(value, PointForecast):
        return (
            value.model_artifact_id,
            value.input.join_id,
            *((value.input.sample_id,) if value.input.sample_id else ()),
        )
    if isinstance(value, PointEvaluation):
        return (
            *value.prediction_ids,
            *(p.target_id for p in value.pairs),
            *((value.test_evaluation_id,) if value.test_evaluation_id else ()),
        )
    if isinstance(value, BaselineComparison):
        return (value.candidate_evaluation_id, value.reference_evaluation_id)
    if isinstance(value, FoldDefinition):
        return (value.dataset_id, value.split_definition_id)
    if isinstance(value, ResearchDatasetManifest):
        # Pin the complete grid hash; expand only the model's explicit TRAIN rows.
        return ()
    if isinstance(value, ResearchSample):
        return (
            value.selection_id,
            *value.feature_vintage_ids,
            *((value.join_id,) if value.join_id else ()),
        )
    if isinstance(value, ResearchSelection):
        return (
            value.request.snapshot_id,
            value.eligibility_id,
            *((value.join_id,) if value.join_id else ()),
        )
    return audit_edges(value)


def lineage_audit(repo: "ModelRepository", root_id: str) -> ModelLineageAudit:
    require(
        root_id.startswith("afre.m_") and not root_id.startswith("afre.m_audit:"),
        "model audit requires a model-layer root",
    )
    seen: set[str] = set()
    active: set[str] = set()
    size = 0

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "model lineage cycle")
        if identity in seen:
            return
        require(
            depth <= repo.model_bounds.audit_depth
            and len(seen) + len(active) < repo.model_bounds.audit_nodes,
            "model audit depth/node bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        if identity.startswith("afre.m_"):
            repo._validate_links(value)
        edges = model_edges(value) or upstream_edges(repo, value)
        extras: tuple[str, ...] = ()
        if isinstance(value, FittedModelArtifact):
            rows = repo._connection.execute(
                "SELECT fingerprint FROM m_fits WHERE artifact_id=?", (identity,)
            ).fetchall()
            require(len(rows) == 1, "model audit requires exact completed fit run")
            # Run → artifact is a provenance back-reference, not a recursive dependency.
            run = repo.resolve(ModelFitRun, rows[0][0])
            repo._validate_links(run)
            extras = (run.fingerprint,)
        for edge in sorted(set(edges)):
            visit(edge, depth + 1)
        for key in (identity, *extras):
            if key not in seen:
                seen.add(key)
                size += len(canonical_json(repo.get_any(key)).encode())
        active.remove(identity)
        require(
            len(seen) <= repo.model_bounds.audit_nodes
            and size <= repo.model_bounds.serialized_bytes,
            "model audit node/byte bound",
        )

    visit(root_id, 0)
    return ModelLineageAudit(
        root_id,
        tuple(seen),
        (
            "exact-frozen-TRAIN-lineage",
            "target-known-by-fit-cutoff",
            "fixed-model-spec",
            "deterministic-solver-replay",
            "explicit-model-and-feature-availability",
            "target-free-prediction-construction",
            "safe-canonical-data-only-artifacts",
        ),
    )
