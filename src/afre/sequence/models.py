"""Bounded fixed decay and diagonal per-observation state dynamics, fitted linear readout."""

import math

from afre.schema import require
from afre.sequence.artifacts import SequenceSnapshot, SequenceTransformArtifact
from afre.sequence.definitions import SequenceModelSpec
from afre.sequence.schema import SequenceFamily
from afre.statistical_models.linear_algebra import finite, total


def temporal_features(
    spec: SequenceModelSpec, snapshot: SequenceSnapshot, state: SequenceTransformArtifact
) -> tuple[
    tuple[float, ...], tuple[tuple[float, ...], ...], tuple[tuple[int, int, float, float], ...]
]:
    require(
        len(state.centers) == len(spec.features) and state.spec_id == spec.fingerprint,
        "temporal model exact transform",
    )
    n, p = len(snapshot.values), len(spec.features)
    weights = [[0.0] * p for _ in range(n)]
    trajectory: list[tuple[float, ...]] = []
    h = [0.0] * p
    terms: list[tuple[int, int, float, float]] = []
    for j in range(p):
        valid = [i for i in range(n) if snapshot.mask[i][j]]
        require(bool(valid), "no effective observations for model feature")
        for order, i in enumerate(valid):
            t = snapshot.observation_times[i]
            assert t is not None
            weights[i][j] = (
                finite(
                    math.exp(
                        -spec.decay_rate_per_second
                        * ((snapshot.origin.availability_cutoff_ns - t) / 1e9)
                    )
                )
                if spec.family is SequenceFamily.EXPONENTIAL_DECAY_LINEAR
                else finite(
                    spec.state_input_gain * spec.state_transition ** (len(valid) - order - 1)
                )
            )
    for i, row in enumerate(snapshot.values):
        for j, raw in enumerate(row):
            if not snapshot.mask[i][j]:
                continue
            assert raw is not None
            value = finite((raw - state.centers[j]) / state.scales[j])
            terms.append((i, j, value, weights[i][j]))
            if spec.family is SequenceFamily.LINEAR_STATE_SPACE:
                h[j] = finite(spec.state_transition * h[j] + spec.state_input_gain * value)
        if (
            snapshot.observation_times[i] is not None
            and spec.family is SequenceFamily.LINEAR_STATE_SPACE
        ):
            trajectory.append(tuple(h))
    aggregates = tuple(
        finite(total(tuple(v * w for _, k, v, w in terms if k == j))) for j in range(p)
    )
    # The closed-form weights are also the exact recurrence contribution oracle.
    if trajectory:
        require(
            all(
                math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
                for a, b in zip(aggregates, trajectory[-1], strict=True)
            ),
            "state recurrence/weights disagree",
        )
    return aggregates, tuple(trajectory), tuple(terms)
