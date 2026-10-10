"""Exact compatible vector comparisons; structural recurrence is descriptive."""

from math import fsum, hypot
from statistics import fmean

from afre.health.artifacts import HealthObservation
from afre.health.definitions import HealthDiagnosticRequest
from afre.health.schema import HealthDiagnostic as D
from afre.statistical_models.metrics import correlation

VECTOR_KINDS = frozenset(
    {
        D.PARAMETER_L1,
        D.PARAMETER_L2,
        D.RELATIVE_PARAMETER,
        D.PARAMETER_SIGN_CHANGES,
        D.PARAMETER_CORRELATION,
        D.RANK_DISPLACEMENT,
        D.TOP_K_OVERLAP,
        D.SIGN_PERSISTENCE,
        D.TREE_SPLIT_RECURRENCE,
        D.TREE_THRESHOLD,
        D.TREE_PATH_RECURRENCE,
        D.TREE_LEAF_SUPPORT,
    }
)


def vector_pair(
    request: HealthDiagnosticRequest,
    left: tuple[HealthObservation, ...],
    right: tuple[HealthObservation, ...],
) -> tuple[float | None, float | None, str]:
    if any("incomparable_parameters" in dict(row.values) for row in (*left, *right)):
        return None, None, "incomparable-raw-scale-or-transform"
    kind = request.kind
    prefixes = {
        D.RANK_DISPLACEMENT: "rank:",
        D.TOP_K_OVERLAP: "rank:",
        D.SIGN_PERSISTENCE: "score:",
        D.TREE_SPLIT_RECURRENCE: "split:",
        D.TREE_THRESHOLD: "threshold:",
        D.TREE_PATH_RECURRENCE: "path:",
        D.TREE_LEAF_SUPPORT: "leaf_support:",
    }
    prefix = prefixes.get(kind, request.column + ":")

    def vector(rows: tuple[HealthObservation, ...]) -> dict[str, float]:
        keys = {
            k for row in rows for k, v in row.values if k.startswith(prefix) and v is not None
        }
        return {
            k: fmean(v for row in rows for name, v in row.values if name == k and v is not None)
            for k in sorted(keys)
        }

    a, b = vector(left), vector(right)
    if not a or not b:
        return None, None, "unsupported-or-empty-parameter-vector"
    if kind in (D.TREE_SPLIT_RECURRENCE, D.TREE_PATH_RECURRENCE):
        return (
            1.0,
            len(set(a) & set(b)) / len(set(a) | set(b)),
            "descriptive-structural-Jaccard",
        )
    if set(a) != set(b):
        return None, None, "incomparable-vector-columns"
    keys = sorted(a)
    av, bv = tuple(a[k] for k in keys), tuple(b[k] for k in keys)
    delta = tuple(y - x for x, y in zip(av, bv, strict=True))
    if kind is D.PARAMETER_CORRELATION:
        return 1.0, correlation(av, bv).value, "descriptive-vector-correlation"
    if kind is D.PARAMETER_SIGN_CHANGES:
        return (
            0.0,
            float(
                sum((x > 0) - (x < 0) != (y > 0) - (y < 0) for x, y in zip(av, bv, strict=True))
            ),
            "exact-sign-change-count",
        )
    if kind is D.PARAMETER_L1:
        norm = fsum(abs(x) for x in av)
        return (
            0.0,
            fsum(abs(x) for x in delta) / norm if norm > request.tolerance else None,
            "normalized-L1-change",
        )
    if kind is D.PARAMETER_L2:
        norm = hypot(*av)
        return (
            0.0,
            hypot(*delta) / norm if norm > request.tolerance else None,
            "normalized-L2-change",
        )
    if kind is D.RELATIVE_PARAMETER:
        return (
            0.0,
            max(abs(d / x) for d, x in zip(delta, av, strict=True))
            if all(abs(x) > request.tolerance for x in av)
            else None,
            "maximum-safe-relative-coefficient-change",
        )
    if kind is D.TOP_K_OVERLAP:
        if len(keys) < request.top_k:
            return None, None, "insufficient-ranked-entities-for-top-K"
        top_a = set(sorted(keys, key=lambda k: (a[k], k))[: request.top_k])
        top_b = set(sorted(keys, key=lambda k: (b[k], k))[: request.top_k])
        return 1.0, len(top_a & top_b) / request.top_k, "lower-ordinal-rank-top-K-overlap"
    if kind is D.SIGN_PERSISTENCE:
        return (
            1.0,
            fmean(
                float((x > 0) - (x < 0) == (y > 0) - (y < 0))
                for x, y in zip(av, bv, strict=True)
            ),
            "matched-entity-sign-persistence",
        )
    if kind is D.RANK_DISPLACEMENT:
        return (
            0.0,
            fmean(abs(x) for x in delta),
            "matched-entity-mean-absolute-rank-displacement",
        )
    return fmean(av), fmean(bv), "exact-compatible-structural-values"
