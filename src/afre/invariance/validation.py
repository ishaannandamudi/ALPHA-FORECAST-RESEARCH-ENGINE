"""Replay completed results from exact immutable data, including relational indexes."""

from typing import TYPE_CHECKING

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
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.splits import TestEvaluation
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.invariance.repository import InvarianceRepository


def validate_invariance(repo: "InvarianceRepository", v: Artifact) -> None:
    from afre.invariance.comparisons import comparison_for, degradation_for, trend_for
    from afre.invariance.diagnostics import model_stability_for
    from afre.invariance.distributions import shift_for
    from afre.invariance.environments import membership_for, validate_definition, validate_set
    from afre.invariance.evaluation import metric_for
    from afre.invariance.forecasts import validate_spec
    from afre.invariance.lineage import audit_for
    from afre.invariance.rankings import predictions_for

    expected: Artifact = v
    if isinstance(v, EnvironmentDefinition):
        validate_definition(repo, v)
    elif isinstance(v, EnvironmentSet):
        validate_set(repo, v)
    elif isinstance(v, StabilityAnalysisSpec):
        validate_spec(repo, v)
    elif isinstance(v, NeutralEnvironmentLabel):
        s = repo.resolve(ResearchSample, v.sample_id)
        require(s.origin == v.origin, "neutral label exact sample origin")
        repo.get_any(v.source.fingerprint)
    elif isinstance(v, EnvironmentMembership):
        with repo.feature_only():
            expected = membership_for(
                repo,
                v.environment_id,
                v.sample_id,
                v.source_ids,
                v.mapping_ids,
                v.constructed_ns,
            )
    elif isinstance(v, EnvironmentMetric):
        seal = (
            repo.resolve(TestEvaluation, v.test_evaluation_id) if v.test_evaluation_id else None
        )
        expected = metric_for(
            repo,
            v.spec_id,
            v.environment_id,
            v.name,
            v.membership_ids,
            v.comparison_environment_ids,
            v.truth_cutoff_ns,
            v.available_ns,
            seal,
        )
    elif isinstance(v, StabilityComparison):
        expected = comparison_for(
            repo, v.left_metric_id, v.right_metric_id, v.available_ns, v.cross_model
        )
    elif isinstance(v, ForecastDegradation):
        expected = degradation_for(repo, v.comparison_id)
    elif isinstance(v, FeatureShiftDiagnostic):
        with repo.feature_only():
            expected = shift_for(
                repo,
                v.spec_id,
                v.feature_reference_id,
                v.environment_ids,
                v.membership_ids,
                v.observation_ids,
                v.cutoff_ns,
                v.available_ns,
            )
    elif isinstance(v, ModelStabilityDiagnostic):
        expected = model_stability_for(
            repo, v.spec_id, v.assignments, v.raw_scale, v.cutoff_ns, v.available_ns
        )
    elif isinstance(v, PredictionStabilityDiagnostic):
        expected = predictions_for(
            repo,
            v.left_spec_id,
            v.right_spec_id,
            v.environment_id,
            v.membership_ids,
            v.cutoff_ns,
            v.available_ns,
        )
    elif isinstance(v, StabilityTrend):
        expected = trend_for(repo, v.metric_ids, v.available_ns)
    elif isinstance(v, StabilityAudit):
        expected = audit_for(repo, v.root_id)
    require(v == expected, "invariance semantic replay mismatch/forged evidence or result")
