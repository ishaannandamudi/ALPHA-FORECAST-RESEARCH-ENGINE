"""Descriptive weight concentration and caller-supplied fit comparisons."""

from math import fsum, log
from typing import TYPE_CHECKING

from afre.fusion.artifacts import FusionArtifact
from afre.fusion.definitions import FusionSpec
from afre.fusion.diagnostics import FusionWeightStability
from afre.schema import require

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository


def weight_diagnostics(
    weights: tuple[tuple[str, float], ...],
) -> tuple[float, float | None, float | None]:
    total = fsum(abs(w) for _, w in weights)
    require(total > 0, "all-zero weights have undefined concentration")
    dominance = max(abs(w) for _, w in weights) / total
    simplex = (
        all(w >= 0 for _, w in weights) and abs(fsum(w for _, w in weights) - 1.0) <= 1e-12
    )
    return (
        dominance,
        (1 / fsum(w * w for _, w in weights) if simplex else None),
        (-fsum(w * log(w) for _, w in weights if w > 0) if simplex else None),
    )


def stability_for(repo: "FusionRepository", ids: tuple[str, ...]) -> FusionWeightStability:
    require(
        1 < len(ids) <= 32 and len(set(ids)) == len(ids), "bounded supplied compatible fits"
    )
    fits = tuple(repo.resolve(FusionArtifact, i) for i in sorted(ids))
    require(all(f.source_ids == fits[0].source_ids for f in fits), "compatible weight columns")
    specs = tuple(repo.get(FusionSpec, f.spec_id) for f in fits)
    require(
        all(
            (
                s.target_id,
                s.horizon_id,
                s.kind,
                s.unit,
                s.family,
                s.normalization,
                s.intercept_policy,
            )
            == (
                specs[0].target_id,
                specs[0].horizon_id,
                specs[0].kind,
                specs[0].unit,
                specs[0].family,
                specs[0].normalization,
                specs[0].intercept_policy,
            )
            for s in specs
        ),
        "weight stability exact model/transform semantics",
    )
    ranges = []
    for j, i in enumerate(fits[0].source_ids):
        values = tuple(f.weights[j][1] for f in fits)
        ranges.append(
            (i, min(values), max(values), len({(v > 0) - (v < 0) for v in values}) == 1)
        )
    return FusionWeightStability(
        tuple(sorted(ids)),
        fits[0].source_ids,
        tuple(ranges),
        tuple((f.fingerprint, weight_diagnostics(f.weights)[0]) for f in fits),
    )
