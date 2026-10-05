"""Explicit pooled least squares on the all-horizon TRAIN intersection."""

import math
from typing import TYPE_CHECKING

from afre.multihorizon.alignment import aligned_rows, training_context
from afre.multihorizon.artifacts import MultiHorizonFitRun, SharedParameters
from afre.multihorizon.definitions import MultiHorizonModelSpec
from afre.multihorizon.schema import Architecture
from afre.schema import require
from afre.statistical_models.linear_algebra import dot, finite, householder_qr, total

if TYPE_CHECKING:
    from afre.multihorizon.repository import MultiHorizonRepository


def fit_for(
    repo: "MultiHorizonRepository",
    spec: MultiHorizonModelSpec,
    started_ns: int,
    completed_ns: int,
    available_ns: int,
) -> tuple[MultiHorizonFitRun, SharedParameters | None]:
    train, matrices = training_context(repo, spec)
    clocks = [repo.get_any(b.point_model_id).available_ns for b in spec.bindings]  # type: ignore[attr-defined]
    for b in spec.bindings:
        if b.probability_model_id:
            clocks.append(repo.get_any(b.probability_model_id).available_ns)  # type: ignore[attr-defined]
        if b.calibration_state_id:
            from afre.calibration.artifacts import CalibrationState

            clocks.append(
                repo.resolve(CalibrationState, b.calibration_state_id).inputs.available_ns
            )
    require(started_ns >= max(clocks), "composition fit precedes underlying model availability")
    cutoff = (
        spec.shared_cutoff_ns
        if spec.shared_cutoff_ns is not None
        else min(t.cutoff_ns for t in train)
    )
    rows = aligned_rows(repo, spec, matrices, cutoff)
    state = None
    if spec.architecture is Architecture.SHARED_LINEAR_BACKBONE:
        require(bool(rows), "shared fit needs all-horizon TRAIN intersection")
        require(
            not spec.bindings[0].preprocessing_state_ids,
            (
                "shared learned transforms require intersection-specific "
                "fitting; supply raw features"
            ),
        )
        columns = matrices[0].feature_ids
        require(
            all(m.feature_ids == columns for m in matrices)
            and all(all(x == r.features[0] for x in r.features) for r in rows),
            "shared features/transforms differ",
        )
        width, count = len(columns), len(spec.bindings)
        require(
            len(rows) * count * (width + count) <= repo.multihorizon_bounds.work_cells,
            "shared dense work bound",
        )
        design, response = [], []
        for row in rows:
            for h, weight in enumerate(spec.horizon_weights):
                scale = finite(math.sqrt(weight))
                design.append(
                    tuple(finite(scale * x) for x in row.features[h])
                    + tuple(scale if k == h else 0.0 for k in range(count))
                )
                response.append(finite(scale * row.responses[h]))
        if spec.ridge_penalty:
            scale = finite(math.sqrt(spec.ridge_penalty))
            design.extend(
                tuple(scale if j == k else 0.0 for j in range(width + count))
                for k in range(width)
            )
            response.extend(0.0 for _ in range(width))
        solution = householder_qr(
            tuple(design), tuple(response), spec.tolerance, spec.condition_limit
        )
        coefficients, intercepts = solution.coefficients[:width], solution.coefficients[width:]
        sse = total(
            [
                finite(w * finite(y - dot(x, coefficients) - intercepts[h]) ** 2)
                for r in rows
                for h, (x, y, w) in enumerate(
                    zip(r.features, r.responses, spec.horizon_weights, strict=True)
                )
            ]
        )
        state = SharedParameters(
            spec.fingerprint,
            columns,
            coefficients,
            intercepts,
            rows,
            cutoff,
            available_ns,
            solution.rank,
            solution.condition_proxy,
            sse,
        )
    run = MultiHorizonFitRun(
        spec.fingerprint,
        train,
        rows,
        state.fingerprint if state else None,
        started_ns,
        completed_ns,
        available_ns,
    )
    repo.check_multihorizon_bounds(run)
    return run, state
