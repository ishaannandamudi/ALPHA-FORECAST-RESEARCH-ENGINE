"""Independent elementary fixture oracles; never used by the fusion engine."""

from math import fsum, sqrt

from afre.fusion import FusionObservation, FusionRepository
from afre.fusion.diagnostics import DiversityMatrix, FusionComparison


def diagnostic_errors(
    repo: FusionRepository, matrix: DiversityMatrix, comparison: FusionComparison
) -> dict[str, float]:
    grid = {
        (o.source_id, o.sample_id): o.value
        for i in matrix.observation_ids
        for o in (repo.get(FusionObservation, i),)
    }
    columns = {i: tuple(grid[i, s] for s in matrix.sample_ids) for i in matrix.source_ids}

    def pearson(a: tuple[float, ...], b: tuple[float, ...]) -> float:
        am, bm = fsum(a) / len(a), fsum(b) / len(b)
        return fsum((x - am) * (y - bm) for x, y in zip(a, b, strict=True)) / sqrt(
            fsum((x - am) ** 2 for x in a) * fsum((y - bm) ** 2 for y in b)
        )

    def ranks(a: tuple[float, ...]) -> tuple[float, ...]:
        return tuple(1.0 + sum(y < x for y in a) + (sum(y == x for y in a) - 1) / 2 for x in a)

    errors = {name: 0.0 for name in ("Pearson", "Spearman", "disagreement", "sign_agreement")}
    for pair in matrix.pairs:
        a = tuple(v for v in columns[pair.left_id] if v is not None)
        b = tuple(v for v in columns[pair.right_id] if v is not None)
        assert pair.pearson.value is not None and pair.spearman.value is not None
        assert pair.mean_absolute_disagreement is not None and pair.sign_agreement is not None
        expected = {
            "Pearson": (pair.pearson.value, pearson(a, b)),
            "Spearman": (pair.spearman.value, pearson(ranks(a), ranks(b))),
            "disagreement": (
                pair.mean_absolute_disagreement,
                fsum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a),
            ),
            "sign_agreement": (
                pair.sign_agreement,
                sum((x > 0) - (x < 0) == (y > 0) - (y < 0) for x, y in zip(a, b, strict=True))
                / len(a),
            ),
        }
        for name, (actual, oracle) in expected.items():
            errors[name] = max(errors[name], abs(actual - oracle))
    truths = tuple(p.truth for p in comparison.pairs)
    center = fsum(truths) / len(truths)
    sst = fsum((y - center) ** 2 for y in truths)

    def metrics(a: tuple[float, ...]) -> dict[str, float]:
        residuals = tuple(x - y for x, y in zip(a, truths, strict=True))
        sse = fsum(v * v for v in residuals)
        return {
            "mse": sse / len(a),
            "mae": fsum(abs(v) for v in residuals) / len(a),
            "r_squared": 1 - sse / sst,
        }

    fused = metrics(tuple(p.fused for p in comparison.pairs))
    errors["fused_metrics"] = max(
        abs(m.value - fused[m.name.value])
        for m in comparison.fused_metrics
        if m.name.value in fused and m.value is not None
    )
    errors["component_metrics"] = 0.0
    errors["metric_deltas"] = 0.0
    for source, ms in comparison.component_metrics:
        component = metrics(tuple(dict(p.component_values)[source] for p in comparison.pairs))
        errors["component_metrics"] = max(
            errors["component_metrics"],
            *(
                abs(m.value - component[m.name.value])
                for m in ms
                if m.name.value in component and m.value is not None
            ),
        )
        errors["metric_deltas"] = max(
            errors["metric_deltas"],
            *(
                abs(v - (fused[n] - component[n]))
                for i, n, v in comparison.deltas
                if i == source and n in component and v is not None
            ),
        )
    return errors
