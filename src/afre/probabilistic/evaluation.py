"""Explicit later truth joins, exact scoring protocols and descriptive comparisons."""

from dataclasses import replace
from typing import TYPE_CHECKING

from afre.probabilistic.artifacts import (
    OriginProbabilityScores,
    ProbabilisticComparison,
    ProbabilisticEvaluation,
    ProbabilisticFitInputs,
    ProbabilisticForecast,
    ProbabilisticModelArtifact,
    ProbabilisticScoredPair,
)
from afre.probabilistic.definitions import (
    ProbabilisticEvaluationProtocol,
    ProbabilisticModelSpec,
)
from afre.probabilistic.schema import ScoreState
from afre.probabilistic.scoring import aggregate_scores, score_forecast
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.statistical_models.artifacts import MatrixExclusion
from afre.statistical_models.linear_algebra import finite
from afre.statistical_models.schema import PredictionScope
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.probabilistic.repository import ProbabilisticRepository


def evaluate_forecasts(
    repo: "ProbabilisticRepository",
    forecast_ids: tuple[str, ...],
    protocol: ProbabilisticEvaluationProtocol,
    cutoff_ns: int,
    available_ns: int,
    seal: TestEvaluation | None = None,
) -> ProbabilisticEvaluation:
    require(
        0 < len(forecast_ids) <= repo.probabilistic_bounds.forecasts
        and len(set(forecast_ids)) == len(forecast_ids),
        "probability evaluation count/duplicates",
    )
    forecasts = tuple(repo.resolve(ProbabilisticForecast, p) for p in forecast_ids)
    first = forecasts[0]
    require(
        all(
            p.model_artifact_id == first.model_artifact_id
            and p.target_definition_id == first.target_definition_id
            and p.input.scope is first.input.scope
            for p in forecasts
        ),
        "probability evaluation cannot mix models, targets/horizons or scopes",
    )
    require(
        sum(
            max(1, len(f.distribution.samples))
            + len(f.quantiles)
            + len(f.threshold_probabilities)
            + len(protocol.intervals)
            for f in forecasts
        )
        <= repo.probabilistic_bounds.work_cells,
        "probability scoring work bound",
    )
    model = repo.resolve(ProbabilisticModelArtifact, first.model_artifact_id)
    spec = repo.resolve(ProbabilisticModelSpec, model.spec_id)
    inputs = repo.resolve(ProbabilisticFitInputs, model.fit_inputs_id)
    if seal is None:
        require(
            first.input.scope is not PredictionScope.TEST,
            "TEST probability evaluation requires access record",
        )
    else:
        require(
            first.input.scope is PredictionScope.TEST
            and seal.fold_id == spec.fold_id
            and seal.evaluated_ns == cutoff_ns,
            "probability TEST record mismatch",
        )
    pairs, exclusions = [], []
    template, _ = score_forecast(first, first.median_value, protocol)
    for forecast in forecasts:
        require(
            forecast.available_ns <= cutoff_ns,
            "probability forecast unavailable at evaluation cutoff",
        )
        require(
            forecast.input.sample_id is not None,
            "probability evaluation requires pinned truth sample",
        )
        assert forecast.input.sample_id is not None
        sample = repo.resolve(ResearchSample, forecast.input.sample_id)
        require(
            sample.origin == forecast.input.origin
            and sample.target_definition_id == spec.target.fingerprint,
            "probability evaluation sample/target mismatch",
        )
        target = repo.resolve(TargetVintage, sample.target_id) if sample.target_id else None
        if target is None or not target_known_by_cutoff(target, cutoff_ns):
            exclusions.append(
                MatrixExclusion(sample.fingerprint, "truth-unavailable-or-unverified-at-cutoff")
            )
            continue
        require(
            seal is None or sample.fingerprint in seal.sample_ids,
            "probability TEST truth outside seal",
        )
        require(
            target.origin == forecast.input.origin and target.definition == spec.target,
            "probability evaluation full target mismatch",
        )
        assert target.value is not None
        scores, pit = score_forecast(forecast, target.value, protocol)
        pairs.append(
            ProbabilisticScoredPair(
                forecast.fingerprint,
                sample.fingerprint,
                target.fingerprint,
                sample.timestamp_ns,
                sample.security.instrument.fingerprint,
                target.value,
                pit,
                scores,
            )
        )
    ordered = tuple(sorted(pairs, key=lambda p: (p.origin_ns, p.security_id, p.sample_id)))
    scores = aggregate_scores(tuple(p.scores for p in ordered), template)
    origins = tuple(
        OriginProbabilityScores(
            at,
            aggregate_scores(tuple(p.scores for p in ordered if p.origin_ns == at), template),
        )
        for at in sorted({p.origin_ns for p in ordered})
    )
    histogram = [0] * protocol.pit_bins
    for pair in ordered:
        if pair.pit is not None:
            histogram[min(protocol.pit_bins - 1, int(pair.pit * protocol.pit_bins))] += 1
    return ProbabilisticEvaluation(
        model.fingerprint,
        inputs.dataset_id,
        spec.fold_id,
        spec.target.fingerprint,
        first.input.scope,
        forecast_ids,
        ordered,
        tuple(exclusions),
        scores,
        origins,
        tuple(histogram),
        protocol,
        cutoff_ns,
        available_ns,
        seal.fingerprint if seal else None,
    )


def comparison_for(
    repo: "ProbabilisticRepository", candidate_id: str, reference_id: str
) -> ProbabilisticComparison:
    left, right = (
        repo.resolve(ProbabilisticEvaluation, candidate_id),
        repo.resolve(ProbabilisticEvaluation, reference_id),
    )
    require(
        (
            left.dataset_id,
            left.fold_id,
            left.target_definition_id,
            left.scope,
            left.evaluation_cutoff_ns,
            left.protocol,
        )
        == (
            right.dataset_id,
            right.fold_id,
            right.target_definition_id,
            right.scope,
            right.evaluation_cutoff_ns,
            right.protocol,
        ),
        "probability comparison protocol differs",
    )

    def evidence(e: ProbabilisticEvaluation) -> tuple[tuple[str, str, float], ...]:
        return tuple((p.sample_id, p.target_id, p.truth) for p in e.pairs)

    require(
        evidence(left) == evidence(right)
        and left.exclusions == right.exclusions
        and len(left.forecast_ids) == len(right.forecast_ids),
        "probability comparison requires identical samples/truth",
    )
    require(
        tuple(s.key for s in left.scores) == tuple(s.key for s in right.scores),
        "probability comparison quantile/threshold protocol differs",
    )
    deltas = tuple(
        replace(
            a,
            value=finite(a.value - b.value)
            if a.value is not None and b.value is not None
            else None,
            state=ScoreState.AVAILABLE
            if a.value is not None and b.value is not None
            else a.state
            if a.value is None
            else b.state,
        )
        for a, b in zip(left.scores, right.scores, strict=True)
    )
    return ProbabilisticComparison(
        candidate_id, reference_id, tuple(p.sample_id for p in left.pairs), deltas
    )
