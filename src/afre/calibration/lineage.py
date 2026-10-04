"""A single bounded traversal spans calibration, raw models and upstream evidence."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import (
    CalibratedForecast,
    CalibrationComparison,
    CalibrationDriftDiagnostics,
    CalibrationEvaluation,
    CalibrationFitInputs,
    CalibrationFitRun,
    CalibrationLineageAudit,
    CalibrationObservationSet,
    CalibrationState,
    ConformalScoreSet,
    ProbabilityMapping,
    QuantileOffset,
)
from afre.calibration.definitions import (
    CalibrationPartition,
    CalibrationRequest,
    CalibrationSpec,
)
from afre.probabilistic.artifacts import ProbabilisticFitRun, ProbabilisticModelArtifact
from afre.probabilistic.lineage import probability_edges
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact, ModelFitRun
from afre.statistical_models.lineage import upstream_edges
from afre.statistical_models.validation import model_edges

if TYPE_CHECKING:
    from afre.calibration.repository import CalibrationRepository


def calibration_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, CalibrationSpec):
        return (
            value.raw_model_id,
            value.raw_spec_id,
            value.target.fingerprint,
            value.partition.fingerprint,
            value.events.fingerprint,
            value.quantiles.fingerprint,
            value.bins.fingerprint,
            *((value.interval.fingerprint,) if value.interval else ()),
        )
    if isinstance(value, CalibrationPartition):
        return value.fold_id, *value.reserved_sample_ids
    if isinstance(value, CalibrationRequest):
        return value.raw_forecast_id, value.target_id
    if isinstance(value, CalibrationObservationSet):
        return (
            value.spec_id,
            *(r.raw_forecast_id for r in value.requests),
            *(r.target_id for r in value.rows),
        )
    if isinstance(value, (ProbabilityMapping, QuantileOffset, ConformalScoreSet)):
        return value.spec_id, value.observations_id
    if isinstance(value, CalibrationFitInputs):
        return value.spec_id, value.raw_model_id, value.observations_id
    if isinstance(value, CalibrationState):
        return (
            value.inputs.fingerprint,
            value.target_definition_id,
            *value.mapping_ids,
            *value.offset_ids,
            *((value.conformal_id,) if value.conformal_id else ()),
            value.diagnostics_id,
        )
    if isinstance(value, CalibrationFitRun):
        return value.inputs.fingerprint, value.state_id, value.diagnostics_id
    if isinstance(value, CalibratedForecast):
        return value.raw_forecast_id, value.state_id
    if isinstance(value, CalibrationEvaluation):
        return value.state_id, value.raw_evaluation_id, *value.forecast_ids
    if isinstance(value, CalibrationComparison):
        return value.raw_evaluation_id, value.calibrated_evaluation_id
    if isinstance(value, CalibrationDriftDiagnostics):
        return value.spec.fingerprint, value.state_id, *value.evaluation_ids
    return ()


def lineage_audit(repo: "CalibrationRepository", root_id: str) -> CalibrationLineageAudit:
    require(
        root_id.startswith("afre.c_") and not root_id.startswith("afre.c_audit:"),
        "calibration audit requires calibration root",
    )
    seen: set[str] = set()
    active: set[str] = set()
    size = 0
    b = repo.calibration_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "calibration lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "calibration audit depth/node bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        if identity.startswith(("afre.c_", "afre.p_", "afre.m_")):
            repo._validate_links(value)
        edges = (
            calibration_edges(value)
            if identity.startswith("afre.c_")
            else probability_edges(value)
            if identity.startswith("afre.p_")
            else model_edges(value) or upstream_edges(repo, value)
        )
        extras: tuple[str, ...] = ()
        if isinstance(
            value, (CalibrationState, ProbabilisticModelArtifact, FittedModelArtifact)
        ):
            table, column, cls = (
                ("c_fits", "state_id", CalibrationFitRun)
                if isinstance(value, CalibrationState)
                else ("p_fits", "artifact_id", ProbabilisticFitRun)
                if isinstance(value, ProbabilisticModelArtifact)
                else ("m_fits", "artifact_id", ModelFitRun)
            )
            rows = repo._connection.execute(
                f"SELECT fingerprint FROM {table} WHERE {column}=?", (identity,)
            ).fetchall()
            require(len(rows) == 1, "calibration audit requires completed fit")
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
            "calibration audit node/byte bound",
        )

    visit(root_id, 0)
    return CalibrationLineageAudit(
        root_id,
        tuple(seen),
        (
            "explicit-reserved-non-TEST-calibration",
            "strict-model-TRAIN-disjointness",
            "raw-forecast-existed-at-origin",
            "truth-known-by-calibration-cutoff",
            "completed-calibration-fit",
            "target-free-application",
            "raw-forecast-preserved",
            "event-quantile-horizon-identity",
            "finite-sample-conformal-rank",
            "canonical-data-only",
        ),
    )
