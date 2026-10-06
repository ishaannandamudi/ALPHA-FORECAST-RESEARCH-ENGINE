"""Feature-only held-out application; no target truth or TRAIN response loads."""

from typing import TYPE_CHECKING

from afre.event_conditioned.forecasts import shifted_distribution
from afre.nonlinear.artifacts import (
    FittedTransformArtifact,
    InteractionValue,
    NonlinearForecast,
    NonlinearInput,
    NonlinearModelArtifact,
    NonlinearProbabilityView,
    TreePathStep,
)
from afre.nonlinear.definitions import NonlinearModelSpec
from afre.nonlinear.interactions import interaction_for
from afre.nonlinear.schema import NonlinearFamily
from afre.nonlinear.sources import validate_input
from afre.nonlinear.trees import tree_prediction
from afre.probabilistic.artifacts import (
    ProbabilisticForecast,
    QuantileValue,
    ThresholdProbability,
)
from afre.probabilistic.distributions import expected_value, quantile
from afre.probabilistic.thresholds import threshold_probability
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import require
from afre.statistical_models.linear_algebra import dot, finite

if TYPE_CHECKING:
    from afre.nonlinear.repository import NonlinearRepository


def forecast_for(
    repo: "NonlinearRepository",
    model: NonlinearModelArtifact,
    inputs: NonlinearInput,
    computed_ns: int,
    base_probability_id: str | None = None,
) -> tuple[NonlinearForecast, tuple[InteractionValue, ...]]:
    spec = repo.resolve(NonlinearModelSpec, model.spec_id)
    partition = validate_input(repo, inputs, spec)
    require(
        partition in (Partition.VALIDATION, Partition.TEST),
        "nonlinear forecasts require held-out samples",
    )
    assert partition is not None
    require(
        model.available_ns <= inputs.origin.availability_cutoff_ns,
        "nonlinear model unavailable at origin",
    )
    states = tuple(repo.resolve(FittedTransformArtifact, i) for i in model.transform_ids)
    mapping = {s.definition_id: s for s in states}
    derived = tuple(
        interaction_for(repo, d, inputs, computed_ns, mapping.get(d.fingerprint))
        for d in spec.interaction_set.definitions
    )
    original = {s.definition.fingerprint: s.value for s in inputs.scalars}
    raw = (
        *tuple(original[f.fingerprint] for f in spec.original_features),
        *tuple(d.value for d in derived),
    )
    require(all(v is not None for v in raw), "model FAIL missing prediction columns")
    values = tuple(
        finite((v - c) / s)
        for v, c, s in zip(raw, model.centers, model.scales, strict=True)
        if v is not None
    )
    contributions: tuple[tuple[str, float], ...] = ()
    path: tuple[TreePathStep, ...] = ()
    if model.family is NonlinearFamily.SHALLOW_REGRESSION_TREE:
        value, path = tree_prediction(model.nodes, model.columns, values)
    else:
        contributions = tuple(
            (identity, finite(coefficient * v))
            for identity, coefficient, v in zip(
                model.columns, model.coefficients, values, strict=True
            )
        )
        value = finite(model.intercept + dot(values, model.coefficients))
    probability = None
    required = max(
        model.available_ns,
        *(s.available_ns for s in states),
        *(s.available_ns for s in inputs.scalars),
        computed_ns,
    )
    if base_probability_id:
        base = repo.resolve(ProbabilisticForecast, base_probability_id)
        require(
            base.input.origin == inputs.origin
            and base.input.sample_id == inputs.sample_id
            and base.target_definition_id == spec.target.fingerprint
            and base.historical_admissible,
            "nonlinear probability exact causal base origin/sample/target",
        )
        required = max(required, base.available_ns)
        base_mean = expected_value(base.distribution)
        require(base_mean is not None, "base probability expectation unsupported")
        assert base_mean is not None
        shift = finite(value - base_mean)
        law = shifted_distribution(base.distribution, shift)
        probability = NonlinearProbabilityView(
            base.fingerprint,
            shift,
            law,
            tuple(QuantileValue(q.level, quantile(law, q.level)) for q in base.quantiles),
            tuple(
                ThresholdProbability(e.request, threshold_probability(law, e.request))
                for e in base.threshold_probabilities
            ),
        )
    require(computed_ns >= required, "nonlinear computation before model/base/input")
    sample = repo.resolve(ResearchSample, inputs.sample_id)
    return NonlinearForecast(
        model.fingerprint,
        spec.fingerprint,
        inputs.fingerprint,
        inputs.sample_id,
        inputs.origin,
        sample.security,
        spec.target.fingerprint,
        partition,
        tuple(d.fingerprint for d in derived),
        values,
        contributions,
        path,
        value,
        probability,
        computed_ns,
        required,
    ), derived
