"""Independent semantic replay at publication and deep audit, with truth-free forecasts."""

from typing import TYPE_CHECKING

from afre.nonlinear.artifacts import (
    FittedTransformArtifact,
    InteractionMatrix,
    InteractionStability,
    InteractionTrainingRow,
    InteractionValue,
    NonlinearAudit,
    NonlinearCalibrationAssessment,
    NonlinearEvaluation,
    NonlinearForecast,
    NonlinearInput,
    NonlinearModelArtifact,
    NonlinearProbabilityView,
    NonlinearRankEvaluation,
    NonlinearRanking,
    ScalarInput,
)
from afre.nonlinear.definitions import InteractionDefinition, InteractionSet, NonlinearModelSpec
from afre.nonlinear.schema import NonlinearBounds
from afre.nonlinear.sources import scalar_for, validate_input
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.nonlinear.repository import NonlinearRepository


def validate_nonlinear(repo: "NonlinearRepository", value: Artifact) -> None:
    if isinstance(value, ScalarInput):
        require(
            value
            == scalar_for(
                repo,
                value.source_id,
                value.origin,
                value.definition.selector,
                value.approved_attestors,
            ),
            "scalar content/clock forgery",
        )
    elif isinstance(value, NonlinearInput):
        validate_input(repo, value)
    elif isinstance(value, InteractionDefinition):
        for feature in value.inputs:
            require(
                repo.get_any(feature.fingerprint) == feature,
                "interaction semantic feature evidence",
            )
    elif isinstance(value, InteractionSet):
        require(
            repo.get_any(value.target.fingerprint) == value.target,
            "interaction exact target evidence",
        )
        for definition in value.definitions:
            require(
                repo.resolve(InteractionDefinition, definition.fingerprint) == definition,
                "interaction exact definition evidence",
            )
    elif isinstance(value, NonlinearModelSpec):
        require(
            repo.resolve(InteractionSet, value.interaction_set.fingerprint)
            == value.interaction_set,
            "model interaction set evidence",
        )
        require(
            repo.resolve_fold(value.fold_id).training_cutoff_ns == value.cutoff_ns,
            "model exact fold cutoff",
        )
        for feature in value.original_features:
            require(
                repo.get_any(feature.fingerprint) == feature, "model original column evidence"
            )
    elif isinstance(value, FittedTransformArtifact):
        from afre.nonlinear.matrix import fit_transform

        spec = repo.resolve(NonlinearModelSpec, value.spec_id)
        definition = repo.resolve(InteractionDefinition, value.definition_id)
        require(
            value
            == fit_transform(
                repo,
                spec,
                definition,
                value.train_input_ids,
                value.started_ns,
                value.completed_ns,
                value.available_ns,
            ),
            "fitted knot/TRAIN evidence forgery",
        )
    elif isinstance(value, InteractionValue):
        from afre.nonlinear.transforms import transform_value

        definition = repo.resolve(InteractionDefinition, value.definition_id)
        scalars = tuple(repo.resolve(ScalarInput, i) for i in value.input_ids)
        require(
            tuple(s.definition for s in scalars) == definition.inputs
            and len({s.origin for s in scalars}) == 1,
            "interaction exact operand order/origin",
        )
        state = (
            repo.resolve(FittedTransformArtifact, value.transform_id)
            if value.transform_id
            else None
        )
        from afre.nonlinear.schema import KnotPolicy

        require(
            (state is not None)
            == (definition.parameters.knot_policy is KnotPolicy.TRAIN_QUANTILES),
            "interaction learned state required",
        )
        require(
            state is None or state.definition_id == definition.fingerprint,
            "interaction exact fitted state",
        )
        required = max(*(s.available_ns for s in scalars), state.available_ns if state else 0)
        expected_value, fallback = transform_value(
            definition, tuple(s.value for s in scalars), state.knots if state else ()
        )
        require(
            value.value == expected_value
            and value.used_fallback == fallback
            and value.computed_ns >= required
            and value.available_ns == value.computed_ns,
            "interaction arithmetic/availability forgery",
        )
    elif isinstance(value, InteractionTrainingRow):
        from afre.research_datasets.samples import ResearchSample
        from afre.research_datasets.schema import Partition
        from afre.target_engine.models import TargetVintage
        from afre.target_engine.validation import target_known_by_cutoff

        spec = repo.resolve(NonlinearModelSpec, value.spec_id)
        inputs = repo.resolve(NonlinearInput, value.input_id)
        require(validate_input(repo, inputs, spec) is Partition.TRAIN, "row TRAIN partition")
        sample = repo.resolve(ResearchSample, value.sample_id)
        target = repo.resolve(TargetVintage, value.target_id)
        derived = tuple(repo.resolve(InteractionValue, i) for i in value.interaction_ids)
        originals = {s.definition.fingerprint: s.value for s in inputs.scalars}
        expected_columns = (
            *tuple(originals[f.fingerprint] for f in spec.original_features),
            *tuple(d.value for d in derived),
        )
        for interaction in derived:
            repo._validate_links(interaction)
        require(
            inputs.sample_id == sample.fingerprint
            and sample.target_id == target.fingerprint
            and target.definition == spec.target
            and target.origin == inputs.origin
            and target_known_by_cutoff(target, spec.cutoff_ns)
            and value.response == target.value
            and tuple(d.definition_id for d in derived)
            == tuple(d.fingerprint for d in spec.interaction_set.definitions)
            and value.values == expected_columns
            and value.available_ns >= target.clocks.final_available_ns
            and all(value.available_ns >= d.available_ns for d in derived),
            "row exact source/target/value forgery",
        )
    elif isinstance(value, NonlinearProbabilityView):
        from afre.event_conditioned.forecasts import shifted_distribution
        from afre.probabilistic.artifacts import (
            ProbabilisticForecast,
            QuantileValue,
            ThresholdProbability,
        )
        from afre.probabilistic.distributions import quantile
        from afre.probabilistic.thresholds import threshold_probability

        base = repo.resolve(ProbabilisticForecast, value.base_forecast_id)
        law = shifted_distribution(base.distribution, value.shift)
        expected_view = NonlinearProbabilityView(
            base.fingerprint,
            value.shift,
            law,
            tuple(QuantileValue(q.level, quantile(law, q.level)) for q in base.quantiles),
            tuple(
                ThresholdProbability(e.request, threshold_probability(law, e.request))
                for e in base.threshold_probabilities
            ),
        )
        require(value == expected_view, "probability shape/quantile/event forgery")
    elif isinstance(value, InteractionMatrix):
        from afre.nonlinear.matrix import matrix_for

        spec = repo.resolve(NonlinearModelSpec, value.spec_id)
        states = tuple(repo.resolve(FittedTransformArtifact, i) for i in value.transform_ids)
        expected, _ = matrix_for(
            repo, spec, tuple(r.input_id for r in value.rows), states, value.computed_ns
        )
        require(value == expected, "TRAIN matrix/source/response forgery")
        for row in value.rows:
            require(repo.get_any(row.fingerprint) == row, "matrix persisted row evidence")
    elif isinstance(value, NonlinearModelArtifact):
        from afre.nonlinear.fitting import fit_model

        spec = repo.resolve(NonlinearModelSpec, value.spec_id)
        matrix = repo.resolve(InteractionMatrix, value.matrix_id)
        repo._validate_links(matrix)
        require(
            value
            == fit_model(
                spec,
                matrix,
                value.started_ns,
                value.completed_ns,
                value.available_ns,
                repo.nonlinear_bounds,
            ),
            "model coefficients/tree/scaling/diagnostics forgery",
        )
    elif isinstance(value, NonlinearForecast):
        from afre.nonlinear.predictions import forecast_for

        model = repo.resolve(NonlinearModelArtifact, value.model_id)
        inputs = repo.resolve(NonlinearInput, value.input_id)
        expected_forecast, _ = forecast_for(
            repo,
            model,
            inputs,
            value.computed_ns,
            value.probability.base_forecast_id if value.probability else None,
        )
        require(value == expected_forecast, "forecast/path/contribution/law/clock forgery")
    elif isinstance(value, NonlinearEvaluation):
        from afre.nonlinear.evaluation import evaluation_for
        from afre.research_datasets.splits import TestEvaluation

        seal = (
            repo.resolve(TestEvaluation, value.test_evaluation_id)
            if value.test_evaluation_id
            else None
        )
        baseline = tuple((p.sample_id, p.baseline_id) for p in value.pairs if p.baseline_id)
        require(
            value
            == evaluation_for(
                repo,
                value.forecast_ids,
                value.cutoff_ns,
                value.available_ns,
                baseline,
                seal,
                value.thresholds,
            ),
            "matched evaluation/truth/metric forgery",
        )
    elif isinstance(value, InteractionStability):
        from afre.nonlinear.stability import stability_for

        require(
            value == stability_for(repo, value.model_ids, value.available_ns),
            "stability arithmetic forgery",
        )
    elif isinstance(value, NonlinearCalibrationAssessment):
        from afre.nonlinear.calibration import assessment_for

        require(
            value
            == assessment_for(
                repo,
                value.forecast_id,
                value.observation_ids,
                value.cutoff_ns,
                value.minimum_count,
                value.proposed_state_id,
            ),
            "calibration compatibility forgery",
        )
    elif isinstance(value, NonlinearRanking):
        from afre.nonlinear.cross_sectional import ranking_for

        require(
            value == ranking_for(repo, value.ranking_id, value.forecast_ids),
            "nonlinear rank bridge forgery",
        )
    elif isinstance(value, NonlinearRankEvaluation):
        from afre.cross_sectional.artifacts import CrossSectionEvaluation

        rank = repo.resolve(NonlinearRanking, value.ranking_id)
        matched = repo.resolve(NonlinearEvaluation, value.matched_id)
        cross = repo.resolve(CrossSectionEvaluation, value.cross_section_id)
        require(
            cross.ranking_id == rank.ranking_id
            and set(matched.forecast_ids) == set(rank.forecast_ids),
            "rank evaluation exact evidence",
        )
    elif isinstance(value, NonlinearAudit):
        from afre.nonlinear.lineage import lineage_for

        require(value == lineage_for(repo, value.root_id), "nonlinear lineage forgery")
    elif not isinstance(value, NonlinearBounds):
        from afre.nonlinear.lineage import nonlinear_edges

        for identity in nonlinear_edges(value):
            repo.get_any(identity)
