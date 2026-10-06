"""One bounded audit traverses forecast, method, assumptions, TRAIN and later truth evidence."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.calibration.lineage import calibration_edges
from afre.cross_sectional.lineage import cross_section_edges
from afre.event_conditioned.lineage import event_edges
from afre.mixture.lineage import mixture_edges
from afre.multihorizon.lineage import multihorizon_edges
from afre.nonlinear.lineage import nonlinear_edges
from afre.probabilistic.artifacts import ProbabilisticModelArtifact
from afre.probabilistic.lineage import probability_edges
from afre.regime_conditioned.lineage import regime_edges
from afre.schema import Artifact, require
from afre.sequence.lineage import sequence_edges
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.lineage import upstream_edges
from afre.statistical_models.validation import model_edges
from afre.uncertainty.artifacts import (
    ForecastUncertaintyDecomposition,
    ParameterCovariance,
    UncertaintyAudit,
    UncertaintyComponent,
    UncertaintyInterval,
)
from afre.uncertainty.definitions import ParameterUncertaintySpec, UncertaintySpec
from afre.uncertainty.evaluation_artifacts import (
    UncertaintyComparison,
    UncertaintyDrift,
    UncertaintyEvaluation,
    UncertaintyEvaluationPair,
)

if TYPE_CHECKING:
    from afre.uncertainty.repository import UncertaintyRepository


def uncertainty_edges(value: Artifact) -> tuple[str, ...]:
    if isinstance(value, ParameterUncertaintySpec):
        return (value.model_id,)
    if isinstance(value, UncertaintySpec):
        return (
            value.target.fingerprint,
            value.forecast_id,
            *(r.fingerprint for r in value.requests),
            *value.alternative_forecast_ids,
            *((value.covariance_id,) if value.covariance_id else ()),
        )
    if isinstance(value, ParameterCovariance):
        return (
            value.spec_id,
            value.model_id,
            value.matrix_id,
            value.target_id,
            value.fold_id,
            *value.train_sample_ids,
        )
    if isinstance(value, UncertaintyComponent):
        return value.spec_id, *value.source_ids, *value.sample_ids
    if isinstance(value, UncertaintyInterval):
        return value.spec_id, value.forecast_id
    if isinstance(value, ForecastUncertaintyDecomposition):
        return (
            value.spec_id,
            value.forecast_id,
            value.target_id,
            value.sample_id,
            value.fold_id,
            value.interval_id,
            *(c.fingerprint for c in value.components),
        )
    if isinstance(value, UncertaintyEvaluationPair):
        return (
            value.evaluation_spec_id,
            value.decomposition_id,
            value.forecast_id,
            value.sample_id,
            value.target_id,
        )
    if isinstance(value, UncertaintyEvaluation):
        return (
            value.evaluation_spec_id,
            *value.decomposition_ids,
            *(p.fingerprint for p in value.pairs),
            *((value.test_evaluation_id,) if value.test_evaluation_id else ()),
        )
    if isinstance(value, UncertaintyComparison):
        return value.left_id, value.right_id
    if isinstance(value, UncertaintyDrift):
        return value.evaluation_ids
    if isinstance(value, UncertaintyAudit):
        return (value.root_id,)
    return ()


def old_edges(repo: "UncertaintyRepository", value: Artifact) -> tuple[str, ...]:
    identity = value.fingerprint
    families = (
        ("afre.sq_", sequence_edges),
        ("afre.nl_", nonlinear_edges),
        ("afre.mix_", mixture_edges),
        ("afre.rc_", regime_edges),
        ("afre.ec_", event_edges),
        ("afre.cs_", cross_section_edges),
        ("afre.mh_", multihorizon_edges),
        ("afre.c_", calibration_edges),
        ("afre.p_", probability_edges),
    )
    for prefix, edges in families:
        if identity.startswith(prefix):
            return edges(value)
    return model_edges(value) or upstream_edges(repo, value)


def lineage_for(repo: "UncertaintyRepository", root_id: str) -> UncertaintyAudit:
    require(
        root_id.startswith("afre.unc_") and not root_id.startswith("afre.unc_audit:"),
        "uncertainty audit requires composition root",
    )
    seen: set[str] = set()
    active: set[str] = set()
    size = 0
    b = repo.uncertainty_bounds

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "uncertainty lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "uncertainty lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        repo._validate_links(value)
        edges = (
            uncertainty_edges(value)
            if identity.startswith("afre.unc_")
            else old_edges(repo, value)
        )
        for edge in sorted(set(edges)):
            visit(edge, depth + 1)
        if isinstance(
            value, (FittedModelArtifact, ProbabilisticModelArtifact, CalibrationState)
        ):
            table, column = (
                ("m_fits", "artifact_id")
                if isinstance(value, FittedModelArtifact)
                else ("p_fits", "artifact_id")
                if isinstance(value, ProbabilisticModelArtifact)
                else ("c_fits", "state_id")
            )
            rows = repo._connection.execute(
                f"SELECT fingerprint FROM {table} WHERE {column}=?", (identity,)
            ).fetchall()
            require(len(rows) == 1, "uncertainty lineage requires completed fit")
            run_id = rows[0][0]
            repo._validate_links(repo.get_any(run_id))
            if run_id not in seen:
                seen.add(run_id)
                size += len(canonical_json(repo.get_any(run_id)).encode())
        active.remove(identity)
        seen.add(identity)
        size += len(canonical_json(value).encode())
        require(
            size <= b.serialized_bytes and len(seen) <= b.audit_nodes,
            "uncertainty lineage byte/node bound",
        )

    visit(root_id, 0)
    return UncertaintyAudit(
        root_id,
        tuple(seen),
        (
            "exact-source-origin-target-horizon-and-availability",
            "explicit-identifiability-and-units",
            "declared-mathematical-closure-only",
            "TRAIN-only-covariance-assumptions",
            "target-free-construction",
            "later-matched-truth-and-TEST-seals",
            "quality-and-disagreement-not-invented-variance",
            "descriptive-diagnostics-no-auto-refit",
            "bounded-unified-lineage",
        ),
    )
