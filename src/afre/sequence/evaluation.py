"""Later exact-truth matched comparisons; no selection and existing TEST seals."""

from typing import TYPE_CHECKING

from afre.event_conditioned.events import EventReference
from afre.mixture.artifacts import MixtureForecast
from afre.mixture.evaluation import metric_deltas, score_mean
from afre.nonlinear.artifacts import InteractionValue, NonlinearForecast, ScalarInput
from afre.nonlinear.probability import probability_scores
from afre.probabilistic.definitions import ThresholdRequest
from afre.regime_conditioned.regimes import RegimeSnapshot
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.sequence.artifacts import (
    SequenceEvaluation,
    SequenceEvaluationPair,
    SequenceForecast,
    SequenceObservation,
    SequenceSnapshot,
)
from afre.sequence.definitions import SequenceModelSpec
from afre.statistical_models.artifacts import PointForecast
from afre.statistical_models.metrics import point_metrics
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


def baseline_value(
    repo: "SequenceRepository", identity: str, forecast: SequenceForecast
) -> float:
    value = repo.get_any(identity)
    if isinstance(value, PointForecast):
        require(
            value.input.origin == forecast.origin
            and value.input.sample_id == forecast.sample_id
            and value.target_definition_id == forecast.target_definition_id
            and value.historical_admissible,
            "matched linear baseline exact origin/sample/target",
        )
    else:
        require(
            isinstance(value, (SequenceForecast, NonlinearForecast, MixtureForecast)),
            "unsupported matched baseline family",
        )
        assert isinstance(value, (SequenceForecast, NonlinearForecast, MixtureForecast))
        sample = (
            value.sample_id
            if isinstance(value, (SequenceForecast, NonlinearForecast))
            else value.request.sample_id
        )
        require(
            value.origin == forecast.origin
            and sample == forecast.sample_id
            and value.target_definition_id == forecast.target_definition_id,
            "matched sequence/mixture baseline",
        )
    require(
        value.available_ns <= forecast.origin.availability_cutoff_ns,
        "baseline causal availability",
    )
    return value.value


def evaluation_for(
    repo: "SequenceRepository",
    ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
    baselines: tuple[tuple[str, str], ...],
    seal: TestEvaluation | None,
    requests: tuple[ThresholdRequest, ...] = (),
) -> SequenceEvaluation:
    require(
        0 < len(ids) <= repo.sequence_bounds.forecasts and len(set(ids)) == len(ids),
        "evaluation forecast bound/duplicates",
    )
    require(
        len(requests) <= 256 and len(set(requests)) == len(requests),
        "evaluation threshold bound/duplicates",
    )
    requests = tuple(sorted(requests, key=lambda t: (t.value, t.comparison.value)))
    forecasts = tuple(repo.resolve(SequenceForecast, i) for i in sorted(ids))
    first = forecasts[0]
    spec = repo.resolve(SequenceModelSpec, first.spec_id)
    require(
        all(f.model_id == first.model_id and f.partition is first.partition for f in forecasts)
        and len({f.sample_id for f in forecasts}) == len(forecasts),
        "evaluation exact model/partition/unique samples",
    )
    require(
        (seal is not None) == (first.partition is Partition.TEST),
        "sequence TEST seal required",
    )
    if seal:
        require(
            seal.fold_id == spec.fold_id and seal.evaluated_ns == cutoff_ns,
            "sequence TEST exact seal",
        )
    baseline_map = dict(baselines)
    require(
        len(baseline_map) == len(baselines)
        and (not baselines or set(baseline_map) == {f.sample_id for f in forecasts}),
        "matched baseline complete exact sample grid",
    )
    pairs = []
    grouped: dict[str, list[SequenceEvaluationPair]] = {}
    for forecast in forecasts:
        sample = repo.resolve(ResearchSample, forecast.sample_id)
        require(
            sample.target_id is not None and forecast.available_ns <= cutoff_ns,
            "evaluation target/forecast unavailable",
        )
        assert sample.target_id is not None
        target = repo.resolve(TargetVintage, sample.target_id)
        require(
            target_known_by_cutoff(target, cutoff_ns)
            and target.origin == forecast.origin
            and target.definition.fingerprint == forecast.target_definition_id
            and (seal is None or sample.fingerprint in seal.sample_ids),
            "evaluation exact known truth/TEST",
        )
        assert target.value is not None
        base_id = baseline_map.get(sample.fingerprint)
        pair = SequenceEvaluationPair(
            forecast.fingerprint,
            sample.fingerprint,
            target.fingerprint,
            forecast.value,
            target.value,
            base_id,
            baseline_value(repo, base_id, forecast) if base_id else None,
            probability_scores(forecast.probability, target.value, requests)
            if forecast.probability
            else (),
        )
        pairs.append(pair)
        cohort_names = {
            "horizon:" + spec.target.horizon.fingerprint,
            "family:" + spec.family.value,
        }
        snapshot = repo.resolve(SequenceSnapshot, forecast.snapshot_id)
        scalars = []
        for identity in {i for row in snapshot.observation_ids for i in row if i}:
            obs = repo.resolve(SequenceObservation, identity)
            source_value = repo.get_any(obs.source_id)
            if isinstance(source_value, ScalarInput):
                scalars.append(source_value)
            else:
                assert isinstance(source_value, InteractionValue)
                scalars.extend(repo.resolve(ScalarInput, i) for i in source_value.input_ids)
        for scalar in scalars:
            source = repo.get_any(scalar.source_id)
            if isinstance(source, EventReference):
                cohort_names.add("event:" + source.event_class.value + ":" + source.subtype)
            elif isinstance(source, RegimeSnapshot):
                cohort_names.add("regime-kind:" + source.membership.kind.value)
                for state, weight in zip(
                    source.membership.states, source.membership.weights, strict=True
                ):
                    if weight > 0:
                        cohort_names.add("regime-active:" + state)
        for name in sorted(cohort_names):
            grouped.setdefault(name, []).append(pair)
    truth = tuple(p.truth for p in pairs)
    metrics = point_metrics(tuple(p.prediction for p in pairs), truth)
    base_metrics = (
        point_metrics(tuple(p.baseline for p in pairs if p.baseline is not None), truth)
        if baselines
        else ()
    )
    return SequenceEvaluation(
        first.model_id,
        tuple(ids),
        tuple(pairs),
        metrics,
        base_metrics,
        metric_deltas(metrics, base_metrics) if baselines else (),
        tuple(
            (
                name,
                point_metrics(
                    tuple(p.prediction for p in group), tuple(p.truth for p in group)
                ),
            )
            for name, group in sorted(grouped.items())
        ),
        score_mean(tuple(p.scores for p in pairs if p.scores)),
        requests,
        cutoff_ns,
        available_ns,
        seal.fingerprint if seal else None,
    )
