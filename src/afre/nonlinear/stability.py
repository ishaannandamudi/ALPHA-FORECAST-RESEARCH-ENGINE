"""Descriptive compatible-window sign/drift/split recurrence without model mutation."""

from typing import TYPE_CHECKING

from afre.nonlinear.artifacts import InteractionStability, NonlinearModelArtifact
from afre.nonlinear.definitions import NonlinearModelSpec
from afre.nonlinear.schema import NonlinearFamily
from afre.schema import require
from afre.statistical_models.linear_algebra import finite

if TYPE_CHECKING:
    from afre.nonlinear.repository import NonlinearRepository


def stability_for(
    repo: "NonlinearRepository", ids: tuple[str, ...], available_ns: int
) -> InteractionStability:
    require(
        2 <= len(ids) <= repo.nonlinear_bounds.evaluations and len(set(ids)) == len(ids),
        "stability input count",
    )
    models = tuple(repo.resolve(NonlinearModelArtifact, i) for i in sorted(ids))
    specs = tuple(repo.resolve(NonlinearModelSpec, m.spec_id) for m in models)
    first = specs[0]
    require(
        all(
            (
                s.target,
                s.interaction_set,
                s.original_features,
                s.family,
                s.preprocessing,
                s.tree,
            )
            == (
                first.target,
                first.interaction_set,
                first.original_features,
                first.family,
                first.preprocessing,
                first.tree,
            )
            for s in specs
        )
        and available_ns >= max(m.available_ns for m in models),
        "compatible stability specs/clocks",
    )
    signs: tuple[float, ...] = ()
    drift: tuple[float, ...] = ()
    recurrence: tuple[float, ...] = ()
    if first.family is NonlinearFamily.SHALLOW_REGRESSION_TREE:
        recurrence = tuple(
            sum(any(n.feature_id == c for n in m.nodes) for m in models) / len(models)
            for c in first.columns
        )
    else:
        raw = tuple(
            tuple(finite(b / s) for b, s in zip(m.coefficients, m.scales, strict=True))
            for m in models
        )
        signs = tuple(
            max(sum((r[j] > 0) - (r[j] < 0) == sign for r in raw) for sign in (-1, 0, 1))
            / len(raw)
            for j in range(len(first.columns))
        )
        drift = tuple(
            finite(max(abs(r[j]) for r in raw) - min(abs(r[j]) for r in raw))
            for j in range(len(first.columns))
        )
    return InteractionStability(
        tuple(ids), first.columns, signs, drift, recurrence, available_ns
    )
