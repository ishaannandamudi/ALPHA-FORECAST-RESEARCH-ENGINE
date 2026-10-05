"""One bounded traversal covers the multi-horizon root and all previous phases."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationFitRun, CalibrationState
from afre.calibration.lineage import calibration_edges
from afre.multihorizon.artifacts import (
    ConsistencyAudit,
    CovarianceArtifact,
    MultiHorizonEvaluation,
    MultiHorizonFitRun,
    MultiHorizonForecast,
    MultiHorizonLineageAudit,
    SharedParameters,
    SharedPointForecast,
)
from afre.multihorizon.definitions import MultiHorizonModelSpec
from afre.multihorizon.horizon_sets import HorizonSet
from afre.probabilistic.artifacts import ProbabilisticFitRun, ProbabilisticModelArtifact
from afre.probabilistic.lineage import probability_edges
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact, ModelFitRun
from afre.statistical_models.lineage import upstream_edges
from afre.statistical_models.validation import model_edges

if TYPE_CHECKING:
    from afre.multihorizon.repository import MultiHorizonRepository


def multihorizon_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, HorizonSet):
        return tuple(t.fingerprint for t in value.targets)
    if isinstance(value, MultiHorizonModelSpec):
        return (
            value.horizon_set.fingerprint,
            *(
                identity
                for b in value.bindings
                for identity in (
                    b.point_spec_id,
                    b.point_model_id,
                    b.feature_set_id,
                    b.fold_id,
                    *b.preprocessing_state_ids,
                    b.probability_spec_id,
                    b.probability_model_id,
                    b.calibration_spec_id,
                    b.calibration_state_id,
                )
                if identity is not None
            ),
        )
    if isinstance(value, MultiHorizonFitRun):
        return (
            value.spec_id,
            *((value.shared_parameters_id,) if value.shared_parameters_id else ()),
            *(t.matrix_id for t in value.train),
        )
    if isinstance(value, SharedParameters):
        return (
            value.spec_id,
            *(i for r in value.sample_rows for i in (*r.sample_ids, *r.target_ids)),
        )
    if isinstance(value, CovarianceArtifact):
        return (
            value.fit_run_id,
            *(i for r in value.rows for i in (*r.sample_ids, *r.target_ids)),
        )
    if isinstance(value, SharedPointForecast):
        return value.fit_run_id, value.shared_parameters_id, value.scaffold_forecast_id
    if isinstance(value, MultiHorizonForecast):
        return (
            value.fit_run_id,
            value.horizon_set_id,
            *((value.covariance_id,) if value.covariance_id else ()),
            *(
                i
                for e in value.entries
                for i in (
                    e.point_forecast_id,
                    e.probability_forecast_id,
                    e.calibrated_forecast_id,
                )
                if i is not None
            ),
        )
    if isinstance(value, ConsistencyAudit):
        return (value.bundle_id,)
    if isinstance(value, MultiHorizonEvaluation):
        return (
            value.fit_run_id,
            *value.bundle_ids,
            *(
                i
                for h in value.horizons
                for i in (
                    h.point_evaluation_id,
                    h.probability_evaluation_id,
                    h.calibration_evaluation_id,
                    h.test_evaluation_id,
                )
                if i is not None
            ),
        )
    return ()


def lineage_audit(repo: "MultiHorizonRepository", root_id: str) -> MultiHorizonLineageAudit:
    require(
        root_id.startswith("afre.mh_") and not root_id.startswith("afre.mh_audit:"),
        "multi-horizon audit requires multi-horizon root",
    )
    seen: set[str] = set()
    active: set[str] = set()
    size = 0
    b = repo.multihorizon_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "multi-horizon lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "multi-horizon audit depth/node bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        if identity.startswith(("afre.mh_", "afre.c_", "afre.p_", "afre.m_")):
            repo._validate_links(value)
        edges = (
            multihorizon_edges(value)
            if identity.startswith("afre.mh_")
            else calibration_edges(value)
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
            require(len(rows) == 1, "multi-horizon audit requires completed fit")
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
            "multi-horizon audit node/byte bound",
        )

    visit(root_id, 0)
    return MultiHorizonLineageAudit(
        root_id,
        tuple(seen),
        (
            "exact-typed-horizons",
            "explicit-parameter-ownership",
            "all-horizon-TRAIN-intersection",
            "horizon-specific-cutoffs",
            "matched-TRAIN-covariance",
            "model-state-known-at-origin",
            "independent-calibration-states",
            "bounded-canonical-data-only",
        ),
    )
