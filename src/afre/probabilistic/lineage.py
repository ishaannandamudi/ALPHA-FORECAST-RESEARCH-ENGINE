"""One bounded lineage traversal spans uncertainty, point fit and upstream evidence."""

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
    ThresholdDefinition,
)
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact, ModelFitRun
from afre.statistical_models.lineage import upstream_edges
from afre.statistical_models.validation import model_edges

if TYPE_CHECKING:
    from afre.probabilistic.repository import ProbabilisticRepository


def probability_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, ProbabilisticModelSpec):
        return (
            value.point_model_id,
            value.fold_id,
            value.target.fingerprint,
            value.quantiles.fingerprint,
            value.thresholds.fingerprint,
            value.scale.fingerprint,
        )
    if isinstance(value, ThresholdDefinition):
        return tuple(r.fingerprint for r in value.requests)
    if isinstance(value, TrainingObservations):
        return (
            value.spec_id,
            value.matrix_id,
            *(r.sample_id for r in value.rows),
            *(r.target_id for r in value.rows),
        )
    if isinstance(value, ProbabilisticFitInputs):
        return (
            value.spec_id,
            value.point_model_id,
            value.point_fit_inputs_id,
            value.observations_id,
        )
    if isinstance(value, TrainingDistribution):
        return value.spec_id, value.observations_id, value.diagnostics.fingerprint
    if isinstance(value, ProbabilisticModelArtifact):
        return value.spec_id, value.fit_inputs_id, value.distribution_id, value.diagnostics_id
    if isinstance(value, ProbabilisticFitRun):
        return (
            value.inputs.fingerprint,
            value.artifact_id,
            value.distribution_id,
            value.diagnostics_id,
        )
    if isinstance(value, ProbabilisticForecast):
        return value.model_artifact_id, value.point_forecast_id
    if isinstance(value, ProbabilisticEvaluationProtocol):
        return tuple(r.fingerprint for r in value.intervals)
    if isinstance(value, ProbabilisticEvaluation):
        return (
            *value.forecast_ids,
            *(p.target_id for p in value.pairs),
            value.protocol.fingerprint,
            *((value.test_evaluation_id,) if value.test_evaluation_id else ()),
        )
    if isinstance(value, ProbabilisticComparison):
        return value.candidate_evaluation_id, value.reference_evaluation_id
    return ()


def lineage_audit(repo: "ProbabilisticRepository", root_id: str) -> ProbabilisticLineageAudit:
    require(
        root_id.startswith("afre.p_") and not root_id.startswith("afre.p_audit:"),
        "probability audit requires model-layer root",
    )
    seen: set[str] = set()
    active: set[str] = set()
    size = 0

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "probability lineage cycle")
        if identity in seen:
            return
        b = repo.probabilistic_bounds
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "probability audit depth/node bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        if identity.startswith(("afre.p_", "afre.m_")):
            repo._validate_links(value)
        edges = (
            probability_edges(value)
            if identity.startswith("afre.p_")
            else model_edges(value) or upstream_edges(repo, value)
        )
        extras: tuple[str, ...] = ()
        if isinstance(value, (ProbabilisticModelArtifact, FittedModelArtifact)):
            table = "p_fits" if isinstance(value, ProbabilisticModelArtifact) else "m_fits"
            cls = (
                ProbabilisticFitRun
                if isinstance(value, ProbabilisticModelArtifact)
                else ModelFitRun
            )
            rows = repo._connection.execute(
                f"SELECT fingerprint FROM {table} WHERE artifact_id=?", (identity,)
            ).fetchall()
            require(len(rows) == 1, "probability audit requires completed fit")
            run = repo.resolve(cls, rows[0][0])
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
            len(seen) <= b.audit_nodes and size <= b.serialized_bytes,
            "probability audit node/byte bound",
        )

    visit(root_id, 0)
    return ProbabilisticLineageAudit(
        root_id,
        tuple(seen),
        (
            "exact-TRAIN-uncertainty",
            "target-known-by-cutoff",
            "explicit-family-scale-centering",
            "completed-point-and-probability-fits",
            "target-free-forecast-construction",
            "monotone-quantiles-and-valid-probabilities",
            "proper-scores-without-calibration",
            "canonical-data-only",
        ),
    )
