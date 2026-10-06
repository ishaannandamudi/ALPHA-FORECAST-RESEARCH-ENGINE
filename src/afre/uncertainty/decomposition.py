"""Only finite-mixture within/between identity supports additive attribution in AFRE-15."""

from typing import TYPE_CHECKING

from afre.mixture.artifacts import MixtureDistribution
from afre.schema import require
from afre.statistical_models.linear_algebra import finite, total
from afre.uncertainty.artifacts import (
    ForecastUncertaintyDecomposition,
    UncertaintyComponent,
    UncertaintyInterval,
)
from afre.uncertainty.components import component_for, units
from afre.uncertainty.definitions import UncertaintySpec
from afre.uncertainty.intervals import interval_for
from afre.uncertainty.moments import variance
from afre.uncertainty.schema import (
    ClosurePolicy,
    IdentifiabilityStatus,
    UncertaintyMeasure,
    UncertaintyType,
)
from afre.uncertainty.sources import source_for

if TYPE_CHECKING:
    from afre.uncertainty.repository import UncertaintyRepository


def close_variance(total_variance: float, values: tuple[float, ...], tolerance: float) -> float:
    finite(total_variance)
    require(
        total_variance >= 0 and all(finite(v) >= 0 for v in values),
        "negative additive variance",
    )
    residual = finite(total_variance - total(list(values)))
    require(
        residual >= -tolerance * max(1.0, total_variance),
        "negative residual outside closure tolerance",
    )
    # Keep the raw arithmetic. Even a tiny negative residual is not silently clamped.
    require(
        residual >= 0,
        "negative residual retained; cannot publish a negative variance component",
    )
    return residual


def decomposition_for(
    repo: "UncertaintyRepository", spec: UncertaintySpec, computed_ns: int
) -> tuple[ForecastUncertaintyDecomposition, UncertaintyInterval]:
    source = source_for(repo, spec.forecast_id)
    require(
        source.target == spec.target
        and computed_ns >= source.available_ns
        and source.origin.timestamp_ns <= computed_ns <= source.origin.availability_cutoff_ns,
        "uncertainty exact target/source/actual computation/cutoff",
    )
    interval = interval_for(spec, source, computed_ns)
    components = tuple(
        component_for(repo, spec, request, source, interval, computed_ns)
        for request in spec.requests
    )
    total_variance = variance(source.law)
    identity = "diagnostics-not-additive-v1"
    error: float | None = None
    shares: tuple[tuple[UncertaintyType, float | None], ...] = ()
    if spec.closure is ClosurePolicy.EXACT_ADDITIVE:
        require(
            isinstance(source.law, MixtureDistribution) and total_variance is not None,
            "exact additive decomposition requires a finite-mixture law",
        )
        assert isinstance(source.law, MixtureDistribution) and total_variance is not None
        require(
            next(
                r for r in spec.requests if r.component is UncertaintyType.TOTAL_PREDICTIVE
            ).measure
            is UncertaintyMeasure.VARIANCE,
            "exact total must be variance",
        )
        additive = tuple(c for c in components if c.additive)
        require(bool(additive), "exact decomposition needs an identified within/between term")
        residual_requested = any(
            c.component is UncertaintyType.RESIDUAL_UNATTRIBUTED for c in components
        )
        if residual_requested:
            residual = close_variance(
                total_variance,
                tuple(c.value for c in additive if c.value is not None),
                spec.tolerance,
            )
            replacement = UncertaintyComponent(
                spec.fingerprint,
                UncertaintyType.RESIDUAL_UNATTRIBUTED,
                UncertaintyMeasure.VARIANCE,
                residual,
                units(spec, UncertaintyMeasure.VARIANCE),
                IdentifiabilityStatus.IDENTIFIED,
                "finite-mixture-unattributed-v1",
                "remainder-of-declared-within-plus-between-identity-no-causal-label",
                (source.artifact.fingerprint, source.law.fingerprint),
                (),
                True,
                computed_ns,
            )
            require(
                next(
                    c
                    for c in components
                    if c.component is UncertaintyType.RESIDUAL_UNATTRIBUTED
                ).measure
                is UncertaintyMeasure.VARIANCE,
                "residual measure must be compatible variance",
            )
            components = tuple(
                replacement if c.component is UncertaintyType.RESIDUAL_UNATTRIBUTED else c
                for c in components
            )
        additive = tuple(
            sorted((c for c in components if c.additive), key=lambda c: c.component.value)
        )
        error = finite(
            total_variance - total([c.value for c in additive if c.value is not None])
        )
        require(
            abs(error) <= spec.tolerance * max(1.0, total_variance),
            "additive uncertainty closure failed",
        )
        identity = "finite-mixture-within-plus-between-v1"
        shares = tuple(
            (
                c.component,
                c.value / total_variance
                if total_variance > 0 and c.value is not None
                else None,
            )
            for c in additive
        )
    return ForecastUncertaintyDecomposition(
        spec.fingerprint,
        source.artifact.fingerprint,
        source.origin,
        spec.target.fingerprint,
        spec.target.horizon.fingerprint,
        source.sample_id,
        source.fold_id,
        source.partition,
        components,
        interval.fingerprint,
        spec.closure,
        identity,
        total_variance,
        error,
        shares,
        source.quality,
        computed_ns,
        computed_ns,
    ), interval
