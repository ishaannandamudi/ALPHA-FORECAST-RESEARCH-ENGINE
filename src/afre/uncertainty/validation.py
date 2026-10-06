"""Semantic replay rejects forged clocks, identifiability, covariance and evaluation."""

from typing import TYPE_CHECKING

from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.splits import TestEvaluation
from afre.schema import Artifact, require
from afre.target_engine.models import TargetVintage
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
    UncertaintyEvaluationSpec,
)

if TYPE_CHECKING:
    from afre.uncertainty.repository import UncertaintyRepository


def validate_uncertainty(repo: "UncertaintyRepository", value: Artifact) -> None:
    if isinstance(value, ParameterUncertaintySpec):
        repo.get_any(value.model_id)
    elif isinstance(value, UncertaintySpec):
        from afre.uncertainty.sources import matched_alternatives, source_for

        with repo.feature_only():
            source = source_for(repo, value.forecast_id)
            require(source.target == value.target, "uncertainty spec exact target/horizon")
            matched_alternatives(repo, source, value.alternative_forecast_ids)
            if value.covariance_id:
                repo.resolve(ParameterCovariance, value.covariance_id)
        for request in value.requests:
            require(
                repo.get_any(request.fingerprint) == request, "uncertainty request persistence"
            )
    elif isinstance(value, ParameterCovariance):
        from afre.uncertainty.parameter import covariance_for

        parameter_policy = repo.resolve(ParameterUncertaintySpec, value.spec_id)
        require(
            value == covariance_for(repo, parameter_policy, value.computed_ns),
            "parameter covariance/assumption/TRAIN/clock forgery",
        )
    elif isinstance(value, (UncertaintyComponent, ForecastUncertaintyDecomposition)):
        from afre.uncertainty.decomposition import decomposition_for

        with repo.feature_only():
            spec = repo.resolve(UncertaintySpec, value.spec_id)
            rebuilt, _ = decomposition_for(
                repo,
                spec,
                value.computed_ns
                if isinstance(value, ForecastUncertaintyDecomposition)
                else value.available_ns,
            )
            require(
                value == rebuilt
                if isinstance(value, ForecastUncertaintyDecomposition)
                else value in rebuilt.components,
                "uncertainty component/total/closure/status forgery",
            )
            if isinstance(value, ForecastUncertaintyDecomposition):
                for component in value.components:
                    require(
                        repo.resolve(UncertaintyComponent, component.fingerprint) == component,
                        "decomposition component persistence",
                    )
                repo.resolve(UncertaintyInterval, value.interval_id)
    elif isinstance(value, UncertaintyInterval):
        from afre.uncertainty.intervals import interval_for
        from afre.uncertainty.sources import source_for

        with repo.feature_only():
            spec = repo.resolve(UncertaintySpec, value.spec_id)
            source = source_for(repo, spec.forecast_id)
            require(
                source.available_ns
                <= value.available_ns
                <= source.origin.availability_cutoff_ns
                and value == interval_for(spec, source, value.available_ns),
                "uncertainty interval/law/clock forgery",
            )
    elif isinstance(value, UncertaintyEvaluationPair):
        from afre.uncertainty.scoring import scores_for
        from afre.uncertainty.sources import source_for

        policy = repo.resolve(UncertaintyEvaluationSpec, value.evaluation_spec_id)
        decomposition = repo.resolve(ForecastUncertaintyDecomposition, value.decomposition_id)
        sample = repo.resolve(ResearchSample, value.sample_id)
        target = repo.resolve(TargetVintage, value.target_id)
        interval = repo.resolve(UncertaintyInterval, decomposition.interval_id)
        source = source_for(repo, value.forecast_id)
        require(
            sample.target_id == target.fingerprint
            and target.origin == decomposition.origin
            and sample.fingerprint == decomposition.sample_id == source.sample_id
            and decomposition.forecast_id == source.artifact.fingerprint
            and value.prediction == source.prediction
            and value.truth == target.value
            and value.variance == decomposition.total_variance
            and value.interval_width == interval.width
            and value.covered
            == (
                interval.lower <= value.truth <= interval.upper
                if interval.lower is not None and interval.upper is not None
                else None
            )
            and value.scores
            == scores_for(
                source,
                value.truth,
                interval.levels,
                policy.thresholds,
                repo.uncertainty_bounds.work_cells,
            ),
            "uncertainty scored truth forgery",
        )
    elif isinstance(value, UncertaintyEvaluation):
        from afre.uncertainty.evaluation import evaluation_for

        policy = repo.resolve(UncertaintyEvaluationSpec, value.evaluation_spec_id)
        seal = (
            repo.resolve(TestEvaluation, value.test_evaluation_id)
            if value.test_evaluation_id
            else None
        )
        require(
            value
            == evaluation_for(
                repo, value.decomposition_ids, policy, value.cutoff_ns, value.available_ns, seal
            ),
            "uncertainty evaluation/coverage/bucket/correlation forgery",
        )
        for pair in value.pairs:
            require(
                repo.resolve(UncertaintyEvaluationPair, pair.fingerprint) == pair,
                "evaluation pair persistence",
            )
    elif isinstance(value, UncertaintyComparison):
        from afre.uncertainty.evaluation import comparison_for

        require(
            value == comparison_for(repo, value.left_id, value.right_id, value.available_ns),
            "matched uncertainty comparison forgery",
        )
    elif isinstance(value, UncertaintyDrift):
        from afre.uncertainty.diagnostics import drift_for

        require(
            value == drift_for(repo, value.evaluation_ids, value.available_ns),
            "uncertainty drift forgery",
        )
    elif isinstance(value, UncertaintyAudit):
        from afre.uncertainty.lineage import lineage_for

        require(value == lineage_for(repo, value.root_id), "uncertainty audit forgery")
    else:
        from afre.uncertainty.lineage import uncertainty_edges

        for identity in uncertainty_edges(value):
            repo.get_any(identity)
