"""Unified bounded native TRAIN, PIT environment, source and later evaluation evidence."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.invariance.artifacts import (
    EnvironmentMembership,
    EnvironmentMetric,
    FeatureShiftDiagnostic,
    ForecastDegradation,
    ModelStabilityDiagnostic,
    NeutralEnvironmentLabel,
    PredictionStabilityDiagnostic,
    StabilityAudit,
    StabilityComparison,
    StabilityTrend,
)
from afre.invariance.definitions import (
    EnvironmentDefinition,
    EnvironmentSet,
    StabilityAnalysisSpec,
)
from afre.orthogonalization.lineage import orthogonalization_edges
from afre.probabilistic.artifacts import ProbabilisticModelArtifact
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.uncertainty.lineage import old_edges, uncertainty_edges

if TYPE_CHECKING:
    from afre.invariance.repository import InvarianceRepository


def invariance_edges(v: Artifact) -> tuple[str, ...]:
    if isinstance(v, EnvironmentDefinition):
        return (
            v.target.fingerprint,
            *v.component_ids,
            *((v.taxonomy_id,) if v.taxonomy_id else ()),
            *((v.universe_definition_id,) if v.universe_definition_id else ()),
        )
    if isinstance(v, EnvironmentSet):
        return tuple(d.fingerprint for d in v.definitions)
    if isinstance(v, StabilityAnalysisSpec):
        return (
            v.target.fingerprint,
            v.fold_id,
            v.environment_set_id,
            *v.sample_ids,
            *v.forecast_ids,
            *v.feature_reference_ids,
            *v.uncertainty_ids,
        )
    if isinstance(v, NeutralEnvironmentLabel):
        return (
            v.sample_id,
            v.source.fingerprint,
            *(
                (v.clocks.historical_delivery.fingerprint,)
                if v.clocks.historical_delivery
                else ()
            ),
        )
    if isinstance(v, EnvironmentMembership):
        return (v.environment_id, v.sample_id, *v.source_ids, *v.mapping_ids)
    if isinstance(v, EnvironmentMetric):
        return (
            v.spec_id,
            v.environment_id,
            *v.membership_ids,
            *v.forecast_ids,
            *v.target_ids,
            *((v.test_evaluation_id,) if v.test_evaluation_id else ()),
        )
    if isinstance(v, StabilityComparison):
        return v.left_metric_id, v.right_metric_id
    if isinstance(v, ForecastDegradation):
        return (v.comparison_id,)
    if isinstance(v, FeatureShiftDiagnostic):
        return (v.spec_id, v.feature_reference_id, *v.membership_ids, *v.observation_ids)
    if isinstance(v, ModelStabilityDiagnostic):
        return (v.spec_id, *(a for _, a in v.assignments), *(e for e, _ in v.assignments))
    if isinstance(v, PredictionStabilityDiagnostic):
        return (
            v.left_spec_id,
            v.right_spec_id,
            *v.membership_ids,
            *v.left_forecast_ids,
            *v.right_forecast_ids,
        )
    if isinstance(v, StabilityTrend):
        return (v.spec_id, *v.metric_ids)
    if isinstance(v, StabilityAudit):
        return (v.root_id,)
    return ()


def audit_for(repo: "InvarianceRepository", root_id: str) -> StabilityAudit:
    require(
        root_id.startswith("afre.inv_") and not root_id.startswith("afre.inv_audit:"),
        "stability audit composition root required",
    )
    b = repo.invariance_bounds
    seen: set[str] = set()
    active: set[str] = set()
    size = 0

    def visit(identity: str, depth: int) -> None:
        nonlocal size
        require(identity not in active, "stability lineage cycle")
        if identity in seen:
            return
        require(
            depth <= b.audit_depth and len(seen) + len(active) < b.audit_nodes,
            "stability lineage node/depth bound",
        )
        active.add(identity)
        value = repo.get_any(identity)
        repo._validate_links(value)
        edges = (
            invariance_edges(value)
            if identity.startswith("afre.inv_")
            else orthogonalization_edges(value)
            if identity.startswith("afre.ort_")
            else uncertainty_edges(value)
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
            runs = repo._connection.execute(
                f"SELECT fingerprint FROM {table} WHERE {column}=?", (identity,)
            ).fetchall()
            require(len(runs) == 1, "stability lineage requires completed native fit")
            run_id = runs[0][0]
            repo._validate_links(repo.get_any(run_id))
            if run_id not in seen:
                seen.add(run_id)
                size += len(canonical_json(repo.get_any(run_id)).encode())
        active.remove(identity)
        seen.add(identity)
        size += len(canonical_json(value).encode())
        require(size <= b.serialized_bytes, "stability lineage byte bound")

    visit(root_id, 0)
    return StabilityAudit(
        root_id,
        tuple(seen),
        (
            "declared-environments-settings-minimum-counts-and-baseline-before-heldout-assessment",
            "exact-target-horizon-frozen-producer-metric-and-sample-intersection",
            "qualified-PIT-source-evidence-and-actual-membership-construction-clocks-separate",
            "later-truth-and-sealed-TEST-evidence-only-in-research-results",
            "input-distribution-shift-separate-from-forecast-error-degradation",
            "measured-coefficients-and-supplied-model-relationships-descriptive-only",
            "stability-across-tested-environments-does-not-prove-causal-invariance",
            "no-significance-profitability-refit-pruning-selection-or-promotion-claim",
            "bounded-canonical-unified-native-TRAIN-source-and-evaluation-lineage",
        ),
    )
