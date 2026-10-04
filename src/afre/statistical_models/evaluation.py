"""Later-cutoff truth joins, sealed TEST access and exact-sample comparisons."""

import math
from statistics import median
from typing import TYPE_CHECKING

from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.statistical_models.artifacts import (
    BaselineComparison,
    EvaluationPair,
    FittedModelArtifact,
    InformationCoefficientSummary,
    MatrixExclusion,
    OriginInformationCoefficient,
    PointEvaluation,
    PointForecast,
    PointMetric,
)
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.linear_algebra import dot, finite, total
from afre.statistical_models.metrics import correlation, point_metrics
from afre.statistical_models.schema import MetricName, MetricState, PredictionScope
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.statistical_models.repository import ModelRepository


def test_record(
    repo: "ModelRepository", fold_id: str, evaluation_id: str, purpose: str, cutoff_ns: int
) -> TestEvaluation:
    ready = tuple(
        s
        for s in repo.partition_samples(fold_id, Partition.TEST)
        if s.target_id is not None
        and target_known_by_cutoff(repo.resolve(TargetVintage, s.target_id), cutoff_ns)
    )
    history = tuple(
        repo.resolve(TestEvaluation, r[0])
        for r in repo._connection.execute(
            "SELECT fingerprint FROM r_artifacts WHERE type_name='TestEvaluation'"
        )
    )
    sample_ids = tuple(sorted(s.fingerprint for s in ready))
    same = next(
        (e for e in history if e.fold_id == fold_id and e.evaluation_id == evaluation_id), None
    )
    if same is not None:
        require(
            same.purpose == purpose
            and same.evaluated_ns == cutoff_ns
            and same.sample_ids == sample_ids,
            "conflicting test evaluation identity reuse",
        )
        return same
    return TestEvaluation(
        fold_id,
        evaluation_id,
        purpose,
        cutoff_ns,
        sample_ids,
        tuple(e.fingerprint for e in history if e.fold_id == fold_id),
    )


def evaluate_forecasts(
    repo: "ModelRepository",
    prediction_ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
    seal: TestEvaluation | None = None,
) -> PointEvaluation:
    require(
        0 < len(prediction_ids) <= repo.model_bounds.predictions
        and len(set(prediction_ids)) == len(prediction_ids),
        "evaluation prediction count/duplicates",
    )
    forecasts = tuple(repo.resolve(PointForecast, p) for p in prediction_ids)
    first = forecasts[0]
    require(
        all(
            p.model_artifact_id == first.model_artifact_id
            and p.target_definition_id == first.target_definition_id
            and p.input.scope is first.input.scope
            for p in forecasts
        ),
        "evaluation cannot mix models, targets/horizons or partitions",
    )
    model = repo.resolve(FittedModelArtifact, first.model_artifact_id)
    spec = repo.resolve(BaselineModelSpec, model.spec_id)
    fold = repo.resolve_fold(spec.fold_id)
    if seal is not None:
        require(
            first.input.scope is PredictionScope.TEST
            and seal.fold_id == spec.fold_id
            and seal.evaluated_ns == cutoff_ns,
            "evaluation TEST record mismatch",
        )
    else:
        require(
            first.input.scope is not PredictionScope.TEST,
            "TEST evaluation requires access record",
        )
    pairs, excluded = [], []
    for forecast in forecasts:
        require(
            forecast.available_ns <= cutoff_ns, "prediction unavailable at evaluation cutoff"
        )
        require(
            forecast.input.sample_id is not None,
            "evaluation requires pinned AFRE-4 truth sample",
        )
        assert forecast.input.sample_id is not None
        sample = repo.resolve(ResearchSample, forecast.input.sample_id)
        require(
            sample.target_definition_id == spec.target.fingerprint,
            "evaluation target/horizon mismatch",
        )
        if seal is not None:
            require(
                sample.fingerprint in seal.sample_ids
                or sample.target_id is None
                or not target_known_by_cutoff(
                    repo.resolve(TargetVintage, sample.target_id), cutoff_ns
                ),
                "TEST sample not admitted by access record",
            )
        target = repo.resolve(TargetVintage, sample.target_id) if sample.target_id else None
        if target is None or not target_known_by_cutoff(target, cutoff_ns):
            excluded.append(
                MatrixExclusion(sample.fingerprint, "truth-unavailable-or-unverified-at-cutoff")
            )
            continue
        require(
            target.origin == forecast.input.origin and target.definition == spec.target,
            "evaluation full origin/target mismatch",
        )
        assert target.value is not None
        pairs.append(
            EvaluationPair(
                forecast.fingerprint,
                sample.fingerprint,
                target.fingerprint,
                sample.timestamp_ns,
                sample.security.instrument.fingerprint,
                forecast.value,
                target.value,
            )
        )
    ordered = tuple(sorted(pairs, key=lambda p: (p.origin_ns, p.security_id, p.sample_id)))
    metrics = point_metrics(
        tuple(p.prediction for p in ordered), tuple(p.truth for p in ordered)
    )
    origins = sorted({p.origin_ns for p in ordered})
    ics = []
    for at in origins:
        group = tuple(p for p in ordered if p.origin_ns == at)
        p, y = tuple(g.prediction for g in group), tuple(g.truth for g in group)
        ics.append(
            OriginInformationCoefficient(
                at, correlation(p, y), correlation(p, y, MetricName.SPEARMAN_CORRELATION)
            )
        )
    pearson = tuple(ic.pearson.value for ic in ics if ic.pearson.value is not None)
    rank = tuple(ic.rank_ic.value for ic in ics if ic.rank_ic.value is not None)

    def summary(values: tuple[float, ...]) -> tuple[float | None, float | None, float | None]:
        if not values:
            return None, None, None
        mean = finite(total(list(values)) / len(values))
        centered = tuple(finite(v - mean) for v in values)
        return (
            mean,
            float(median(values)),
            finite(math.sqrt(dot(centered, centered) / len(values))),
        )

    ic_summary = InformationCoefficientSummary(
        len(ics), len(pearson), len(rank), *summary(pearson), *summary(rank)
    )
    return PointEvaluation(
        model.fingerprint,
        fold.dataset_id,
        spec.fold_id,
        spec.target.fingerprint,
        first.input.scope,
        prediction_ids,
        ordered,
        tuple(excluded),
        metrics,
        tuple(ics),
        ic_summary,
        cutoff_ns,
        available_ns,
        seal.fingerprint if seal else None,
    )


def comparison_for(
    repo: "ModelRepository", candidate_id: str, reference_id: str
) -> BaselineComparison:
    left, right = (
        repo.resolve(PointEvaluation, candidate_id),
        repo.resolve(PointEvaluation, reference_id),
    )
    require(
        (
            left.dataset_id,
            left.fold_id,
            left.target_definition_id,
            left.scope,
            left.evaluation_cutoff_ns,
        )
        == (
            right.dataset_id,
            right.fold_id,
            right.target_definition_id,
            right.scope,
            right.evaluation_cutoff_ns,
        ),
        "comparison evaluation protocol differs",
    )
    evidence_left = tuple((p.sample_id, p.target_id, p.truth) for p in left.pairs)
    evidence_right = tuple((p.sample_id, p.target_id, p.truth) for p in right.pairs)
    require(
        evidence_left == evidence_right
        and left.exclusions == right.exclusions
        and len(left.prediction_ids) == len(right.prediction_ids),
        "comparison requires exact same samples/truth",
    )
    right_metrics = {m.name: m for m in right.metrics}
    deltas = []
    for metric in left.metrics:
        other = right_metrics[metric.name]
        if metric.value is not None and other.value is not None:
            deltas.append(
                PointMetric(
                    metric.name,
                    finite(metric.value - other.value),
                    MetricState.AVAILABLE,
                    metric.sample_count,
                )
            )
        else:
            state = metric.state if metric.value is None else other.state
            deltas.append(PointMetric(metric.name, None, state, metric.sample_count))
    return BaselineComparison(
        candidate_id, reference_id, tuple(p.sample_id for p in left.pairs), tuple(deltas)
    )
