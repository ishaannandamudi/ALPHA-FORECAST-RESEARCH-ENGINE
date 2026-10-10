"""Frozen fused-vs-component common truth intersection; no tuning or reselection."""

from math import fsum
from typing import TYPE_CHECKING

from afre.fusion.accounting import FusionTrialPool
from afre.fusion.artifacts import (
    FrozenFusionTestChoice,
    FusedForecast,
    FusionArtifact,
    FusionObservation,
)
from afre.fusion.definitions import FusionSpec
from afre.fusion.diagnostics import FusionComparison, FusionEvaluationPair
from afre.fusion.probabilistic import blend, crps, nll
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.statistical_models.metrics import correlation, point_metrics
from afre.statistical_models.schema import MetricName
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository


def comparison_for(
    repo: "FusionRepository",
    ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
    choice_id: str | None = None,
    seal_id: str | None = None,
    pool_id: str | None = None,
) -> FusionComparison:
    require(
        0 < len(ids) <= repo.fusion_bounds.prediction_rows and len(set(ids)) == len(ids),
        "comparison forecast bound/duplicates",
    )
    with repo.feature_only():
        forecasts = tuple(repo.resolve(FusedForecast, i) for i in sorted(ids))
    first = forecasts[0]
    require(
        all(
            f.artifact_id == first.artifact_id
            and f.partition is first.partition
            and f.available_ns <= cutoff_ns
            for f in forecasts
        )
        and len({f.sample_id for f in forecasts}) == len(forecasts),
        "one frozen artifact/partition; exact distinct samples",
    )
    artifact = repo.get(FusionArtifact, first.artifact_id)
    spec = repo.get(FusionSpec, artifact.spec_id)
    require(pool_id is not None, "comparison requires explicit AFRE19 trial pool")
    assert pool_id is not None
    pool = repo.resolve(FusionTrialPool, pool_id)
    require(
        spec.fingerprint in pool.spec_ids and spec.fingerprint not in pool.failed_spec_ids,
        "comparison exact registered fusion opportunity",
    )
    require(
        (spec.output_unit or spec.unit) == "target-value:" + spec.target_id,
        "signal evaluation requires explicit normalized target-unit contract",
    )
    require(
        first.partition in (Partition.VALIDATION, Partition.TEST), "held-out evaluation only"
    )
    if first.partition is Partition.TEST:
        require(
            choice_id is not None and seal_id is not None,
            "TEST frozen choice and access record required",
        )
        assert choice_id is not None and seal_id is not None
        choice = repo.resolve(FrozenFusionTestChoice, choice_id)
        seal = repo.resolve(TestEvaluation, seal_id)
        require(
            choice.artifact_id == first.artifact_id
            and seal.fold_id == spec.fold_id
            and seal.evaluated_ns == cutoff_ns
            and {f.sample_id for f in forecasts} <= set(seal.sample_ids),
            "TEST exact frozen authority",
        )
    else:
        require(
            choice_id is None and seal_id is None, "VALIDATION cannot borrow TEST authority"
        )
    pairs, exclusions, laws = [], [], {}
    for f in forecasts:
        with repo.feature_only():
            obs = tuple(repo.resolve(FusionObservation, i) for i in f.observation_ids)
        grid = {o.source_id: o for o in obs if o.value is not None}
        sample = repo.get(ResearchSample, f.sample_id)
        target = repo.resolve(TargetVintage, sample.target_id) if sample.target_id else None
        if f.value is None or set(grid) != set(spec.source_ids):
            exclusions.append((f.sample_id, "incomplete-common-component-intersection"))
        elif (
            target is None
            or not target_known_by_cutoff(target, cutoff_ns)
            or target.value is None
        ):
            exclusions.append((f.sample_id, "truth-unavailable-at-cutoff"))
        else:
            require(
                target.origin == f.origin and target.definition.fingerprint == spec.target_id,
                "exact comparison truth",
            )
            component_values = tuple((i, grid[i].value) for i in spec.source_ids)
            pairs.append(
                FusionEvaluationPair(
                    f.sample_id,
                    f.fingerprint,
                    target.fingerprint,
                    target.value,
                    f.value,
                    tuple((i, v) for i, v in component_values if v is not None),
                )
            )
            if f.law is not None and all(grid[i].law is not None for i in spec.source_ids):
                laws[f.sample_id] = (f.law, grid)
    pairs = sorted(pairs, key=lambda p: p.sample_id)
    truths = tuple(p.truth for p in pairs)
    fused = point_metrics(tuple(p.fused for p in pairs), truths)
    components = tuple(
        (i, point_metrics(tuple(dict(p.component_values)[i] for p in pairs), truths))
        for i in spec.source_ids
    )
    delta_items = []
    for i, ms in components:
        by_name = {m.name: m.value for m in ms}
        for metric in fused:
            other = by_name[metric.name]
            delta_items.append(
                (
                    i,
                    metric.name.value,
                    metric.value - other
                    if metric.value is not None and other is not None
                    else None,
                )
            )
    deltas = tuple(delta_items)
    scores = []
    for i in (artifact.fingerprint, *spec.source_ids):
        crps_values, nll_values = [], []
        for p in pairs:
            if p.sample_id not in laws:
                continue
            law, grid = laws[p.sample_id]
            if i != artifact.fingerprint:
                o = grid[i]
                assert o.law is not None
                law = blend(
                    ((i, o.output_id, 1.0, o.law),), repo.fusion_bounds.probability_components
                )
            crps_values.append(crps(law, p.truth))
            score = nll(law, p.truth)
            if score is not None:
                nll_values.append(score)
        for name, values in (("CRPS", crps_values), ("NLL", nll_values)):
            scores.append(
                (
                    i,
                    name,
                    fsum(values) / len(values)
                    if len(values) == len(pairs) and values
                    else None,
                )
            )
    origins = {f.sample_id: f.origin.timestamp_ns for f in forecasts}
    ic = []
    for i in (artifact.fingerprint, *spec.source_ids):
        for at in sorted(set(origins[p.sample_id] for p in pairs)):
            group = tuple(p for p in pairs if origins[p.sample_id] == at)
            predictions = tuple(
                p.fused if i == artifact.fingerprint else dict(p.component_values)[i]
                for p in group
            )
            y = tuple(p.truth for p in group)
            ic.append(
                (
                    i,
                    at,
                    correlation(predictions, y).value,
                    correlation(predictions, y, MetricName.SPEARMAN_CORRELATION).value,
                )
            )
    return FusionComparison(
        first.artifact_id,
        ids,
        tuple(pairs),
        tuple(exclusions),
        fused,
        components,
        deltas,
        tuple(scores),
        tuple(ic),
        cutoff_ns,
        available_ns,
        choice_id,
        seal_id,
        pool_id,
    )
