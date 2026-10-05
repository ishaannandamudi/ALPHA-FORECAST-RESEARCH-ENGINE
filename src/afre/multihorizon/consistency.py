"""Mathematically valid compatibility diagnostics; no invented scaling laws."""

from typing import TYPE_CHECKING

from afre.horizons import HorizonBasis
from afre.multihorizon.artifacts import ConsistencyAudit, MultiHorizonForecast
from afre.multihorizon.forecasts import surfaces
from afre.multihorizon.horizon_sets import HorizonSet
from afre.statistical_models.linear_algebra import finite
from afre.target_engine.definitions import TargetDefinition, TargetEndpointRules

if TYPE_CHECKING:
    from afre.multihorizon.repository import MultiHorizonRepository


def compatible_units(targets: tuple[TargetDefinition, ...]) -> bool:
    return (
        len(
            {
                (
                    t.target_type,
                    t.aggregation,
                    t.benchmark,
                    t.path.annualization_factor if t.path else None,
                )
                for t in targets
            }
        )
        == 1
    )


def consistency_for(
    repo: "MultiHorizonRepository", bundle: MultiHorizonForecast
) -> ConsistencyAudit:
    horizons = repo.resolve(HorizonSet, bundle.horizon_set_id)
    targets = horizons.targets
    same = compatible_units(targets)
    adjusted = len({t.adjustment for t in targets}) == 1
    nested = all(
        t.horizon.basis is HorizonBasis.ELAPSED_TIME and t.endpoints == TargetEndpointRules()
        for t in targets
    ) and all(
        (a.horizon.duration_ns or 0) < (b.horizon.duration_ns or 0)
        for a, b in zip(targets, targets[1:], strict=False)
    )
    expected, _, _ = surfaces(repo, bundle)
    differences = tuple(
        finite(b.value - a.value)
        if same and adjusted and a.value is not None and b.value is not None
        else None
        for a, b in zip(expected, expected[1:], strict=False)
    )
    return ConsistencyAudit(
        bundle.fingerprint,
        same,
        adjusted,
        nested,
        (
            "exact-ordered-targets",
            "same-full-origin-security",
            "within-horizon-quantile-order",
            "nested-simple-returns-not-additive",
            "quantiles-not-additive",
            "no-variance-horizon-scaling",
            "covariance-descriptive-not-causal",
        ),
        differences,
    )
