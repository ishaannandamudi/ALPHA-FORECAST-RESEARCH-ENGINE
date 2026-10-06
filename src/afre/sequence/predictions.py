"""Feature-only causal forecast; exact temporal contributions and optional preserved law."""

from typing import TYPE_CHECKING

from afre.event_conditioned.forecasts import shifted_distribution
from afre.nonlinear.artifacts import NonlinearProbabilityView
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
from afre.sequence.artifacts import (
    SequenceContribution,
    SequenceForecast,
    SequenceModelArtifact,
    SequenceSnapshot,
    SequenceTransformArtifact,
)
from afre.sequence.datasets import validate_snapshot_input
from afre.sequence.definitions import SequenceModelSpec
from afre.sequence.models import temporal_features
from afre.statistical_models.linear_algebra import finite, total

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


def forecast_for(
    repo: "SequenceRepository",
    model: SequenceModelArtifact,
    sample_id: str,
    snapshot: SequenceSnapshot,
    computed_ns: int,
    base_probability_id: str | None = None,
) -> SequenceForecast:
    spec = repo.resolve(SequenceModelSpec, model.spec_id)
    sample = repo.resolve(ResearchSample, sample_id)
    partition = validate_snapshot_input(repo, spec, sample, snapshot)
    require(
        partition in (Partition.VALIDATION, Partition.TEST),
        "sequence held-out application only",
    )
    state = repo.resolve(SequenceTransformArtifact, model.transform_id)
    aggregates, trajectory, terms = temporal_features(spec, snapshot, state)
    contributions = []
    for i, j, value, weight in terms:
        identity = snapshot.observation_ids[i][j]
        assert identity is not None
        contributions.append(
            SequenceContribution(
                snapshot.feature_ids[j],
                identity,
                value,
                weight,
                model.coefficients[j],
                finite(value * weight * model.coefficients[j]),
            )
        )
    prediction = finite(model.intercept + total(tuple(c.contribution for c in contributions)))
    required = max(model.available_ns, state.available_ns, snapshot.available_ns, computed_ns)
    probability = None
    if base_probability_id:
        base = repo.resolve(ProbabilisticForecast, base_probability_id)
        require(
            base.input.origin == snapshot.origin
            and base.input.sample_id == sample_id
            and base.target_definition_id == spec.target.fingerprint
            and base.historical_admissible,
            "sequence exact causal base origin/sample/target",
        )
        mean = expected_value(base.distribution)
        require(mean is not None, "sequence base expectation unsupported")
        assert mean is not None
        shift = finite(prediction - mean)
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
        required = max(required, base.available_ns)
    require(computed_ns >= required, "sequence actual computation before inputs/model/base")
    return SequenceForecast(
        model.fingerprint,
        spec.fingerprint,
        snapshot.fingerprint,
        sample.fingerprint,
        snapshot.origin,
        sample.security,
        spec.target.fingerprint,
        partition,
        prediction,
        aggregates,
        tuple(contributions),
        trajectory,
        probability,
        computed_ns,
        required,
    )
