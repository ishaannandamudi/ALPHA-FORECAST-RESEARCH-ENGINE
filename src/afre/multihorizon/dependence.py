"""Dependence state uses matched TRAIN residuals, never held-out outcomes."""

from typing import TYPE_CHECKING

from afre.multihorizon.alignment import aligned_rows, training_context
from afre.multihorizon.artifacts import CovarianceArtifact, MultiHorizonFitRun
from afre.multihorizon.covariance import empirical_covariance
from afre.multihorizon.definitions import MultiHorizonModelSpec
from afre.multihorizon.schema import Architecture, Denominator
from afre.schema import require
from afre.statistical_models.linear_algebra import dot, finite

if TYPE_CHECKING:
    from afre.multihorizon.repository import MultiHorizonRepository


def covariance_for(
    repo: "MultiHorizonRepository",
    run: MultiHorizonFitRun,
    cutoff_ns: int,
    available_ns: int,
    denominator: Denominator,
    tolerance: float,
) -> CovarianceArtifact:
    spec = repo.resolve(MultiHorizonModelSpec, run.spec_id)
    _, matrices = training_context(repo, spec)
    rows = aligned_rows(repo, spec, matrices, cutoff_ns)
    if spec.architecture is Architecture.SHARED_LINEAR_BACKBONE:
        from dataclasses import replace

        from afre.multihorizon.artifacts import SharedParameters

        state = repo.resolve(SharedParameters, run.shared_parameters_id or "")
        rows = tuple(
            replace(
                r,
                residuals=tuple(
                    finite(y - dot(x, state.coefficients) - intercept)
                    for x, y, intercept in zip(
                        r.features, r.responses, state.intercepts, strict=True
                    )
                ),
            )
            for r in rows
        )
    require(
        available_ns >= max(run.available_ns, cutoff_ns), "dependence availability precedes fit"
    )
    require(
        len(rows) * len(spec.bindings) ** 2 <= repo.multihorizon_bounds.work_cells,
        "covariance work bound",
    )
    means, matrix = empirical_covariance(tuple(r.residuals for r in rows), denominator)
    return CovarianceArtifact(
        run.fingerprint,
        tuple(h.fingerprint for h in spec.horizon_set.horizons),
        rows,
        means,
        matrix,
        denominator,
        cutoff_ns,
        available_ns,
        tolerance,
    )
