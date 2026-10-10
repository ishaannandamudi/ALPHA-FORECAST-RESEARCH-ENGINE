"""Prediction diversity is separate from quality and cannot change frozen weights."""

from math import fsum
from typing import TYPE_CHECKING

from afre.fusion.artifacts import FusionObservation
from afre.fusion.definitions import FusionSourceReference
from afre.fusion.diagnostics import DiversityMatrix, FusionPairDiversity
from afre.research_datasets.samples import ResearchSample
from afre.schema import require
from afre.statistical_models.metrics import correlation
from afre.statistical_models.schema import MetricName
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository


def diversity_for(
    repo: "FusionRepository",
    source_ids: tuple[str, ...],
    ids: tuple[str, ...],
    available_ns: int,
    cutoff_ns: int | None = None,
) -> DiversityMatrix:
    source_ids = tuple(sorted(source_ids))
    require(
        0 < len(source_ids) <= repo.fusion_bounds.sources
        and len(set(source_ids)) == len(source_ids)
        and len(source_ids) ** 2 <= repo.fusion_bounds.diversity_cells
        and len(ids) <= repo.fusion_bounds.prediction_rows * len(source_ids),
        "diversity configured bounds",
    )
    with repo.feature_only():
        refs = tuple(repo.resolve(FusionSourceReference, i) for i in source_ids)
        require(
            len({(r.target_id, r.horizon_id, r.kind, r.unit) for r in refs}) == 1,
            "diversity requires compatible target/horizon/kind/unit",
        )
        obs = tuple(repo.resolve(FusionObservation, i) for i in sorted(ids))
    require(
        len({(o.source_id, o.sample_id) for o in obs}) == len(obs)
        and all(o.source_id in source_ids and o.available_ns <= available_ns for o in obs),
        "diversity exact source/sample grid",
    )
    grid = {
        i: {o.sample_id: o for o in obs if o.source_id == i and o.value is not None}
        for i in source_ids
    }
    common = set.intersection(*(set(v) for v in grid.values()))
    union = {o.sample_id for o in obs}
    truths: dict[str, TargetVintage] = {}
    if cutoff_ns is not None:
        require(not repo._feature_only_depth, "error diversity requires later evaluation truth")
        for sample_id in sorted(common):
            sample = repo.get(ResearchSample, sample_id)
            require(
                repo._connection.execute(
                    "SELECT 1 FROM r_memberships WHERE sample_id=? AND partition='test'",
                    (sample_id,),
                ).fetchone()
                is None,
                "TEST error diversity requires sealed evaluation (unsupported here)",
            )
            if sample.target_id:
                target = repo.resolve(TargetVintage, sample.target_id)
                if target_known_by_cutoff(target, cutoff_ns):
                    truths[sample_id] = target
        common.intersection_update(truths)
    samples = tuple(sorted(common))
    require(len(samples) <= repo.fusion_bounds.prediction_rows, "diversity row bound")
    truth_values = {s: t.value for s, t in truths.items() if t.value is not None}
    columns = {i: tuple(grid[i][s].value for s in samples) for i in source_ids}
    pairs = []
    for i in source_ids:
        for j in source_ids:
            a = tuple(v for v in columns[i] if v is not None)
            b = tuple(v for v in columns[j] if v is not None)
            error = (
                correlation(
                    tuple(
                        v - truth_values[s]
                        for v, s in zip(a, samples, strict=True)
                        if truth_values[s] is not None
                    ),
                    tuple(
                        v - truth_values[s]
                        for v, s in zip(b, samples, strict=True)
                        if truth_values[s] is not None
                    ),
                )
                if cutoff_ns is not None
                else None
            )
            pairs.append(
                FusionPairDiversity(
                    i,
                    j,
                    correlation(a, b),
                    correlation(a, b, MetricName.SPEARMAN_CORRELATION),
                    error,
                    fsum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a) if a else None,
                    sum(
                        (x > 0) - (x < 0) == (y > 0) - (y < 0)
                        for x, y in zip(a, b, strict=True)
                    )
                    / len(a)
                    if a
                    else None,
                )
            )
    return DiversityMatrix(
        source_ids,
        ids,
        samples,
        tuple(union - common),
        tuple(pairs),
        tuple(truths[s].fingerprint for s in samples) if cutoff_ns is not None else (),
        cutoff_ns,
        available_ns,
    )
