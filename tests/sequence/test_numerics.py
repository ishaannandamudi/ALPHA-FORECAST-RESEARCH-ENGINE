"""Exact independent decay and masked diagonal recurrence fixtures."""

import math
from dataclasses import replace

import pytest

from afre.sequence import (
    SequenceFamily,
    SequencePreprocessing,
    SequenceTransformArtifact,
    SequenceWindowMode,
    SequenceWindowSpec,
)
from afre.sequence.models import temporal_features
from tests.sequence.conftest import Case


@pytest.mark.parametrize("family", list(SequenceFamily))
def test_exact_temporal_weights_and_mask(case: Case, family: SequenceFamily) -> None:
    origin = replace(
        case.forecast.origin, timestamp_ns=3_000_000_000, availability_cutoff_ns=3_000_000_000
    )
    observations = (
        case.observe(1_000_000_000, 2.0),
        case.observe(1_500_000_000, None),
        case.observe(2_000_000_000, 4.0),
    )
    window = SequenceWindowSpec(SequenceWindowMode.FIXED_OBSERVATION_COUNT, 5)
    spec = replace(
        case.fixture.specs[0],
        features=(case.micro,),
        window=window,
        family=family,
        preprocessing=SequencePreprocessing.NONE,
        decay_rate_per_second=math.log(2),
        state_transition=0.5,
        state_input_gain=2.0,
    )
    snap = case.engine.snapshot(
        origin,
        spec.features,
        window,
        origin.timestamp_ns,
        tuple(o.fingerprint for o in observations),
    )
    state = SequenceTransformArtifact(
        spec.fingerprint, case.fixture.bindings, (0.0,), (1.0,), (2,), 40, 40, 40, 40
    )
    aggregates, trajectory, terms = temporal_features(spec, snap, state)
    expected = (
        2 * 0.25 + 4 * 0.5
        if family is SequenceFamily.EXPONENTIAL_DECAY_LINEAR
        else 0.5 * (2 * 2) + 2 * 4
    )
    assert aggregates == pytest.approx((expected,))
    assert tuple(t[3] for t in terms) == pytest.approx(
        (0.25, 0.5) if family is SequenceFamily.EXPONENTIAL_DECAY_LINEAR else (1.0, 2.0)
    )
    if trajectory:
        assert trajectory == ((4.0,), (4.0,), (10.0,))
    assert len(terms) == 2 and snap.mask[:2] == ((False,), (False,))


@pytest.mark.parametrize("index", [0, 1])
def test_independent_ridge_readout(case: Case, index: int) -> None:
    from afre.sequence import SequenceDataset, SequenceSnapshot
    from examples.sequence_oracles import ridge_oracle

    model, spec = case.fixture.models[index], case.fixture.specs[index]
    dataset = case.repo.get(SequenceDataset, model.dataset_id)
    state = case.repo.get(SequenceTransformArtifact, model.transform_id)
    # Independent extraction of declared weights (does not call the model implementation).
    rows = []
    for row in dataset.rows:
        snapshot = case.repo.get(SequenceSnapshot, row.snapshot_id)
        aggregates = []
        for j in range(len(spec.features)):
            values = [
                (t, v[j])
                for t, v in zip(snapshot.observation_times, snapshot.values, strict=True)
                if v[j] is not None
            ]
            aggregate = 0.0
            for t, v in values:
                assert t is not None and v is not None
                value = (v - state.centers[j]) / state.scales[j]
                if index == 0:
                    aggregate += (
                        math.exp(
                            -spec.decay_rate_per_second
                            * (snapshot.origin.availability_cutoff_ns - t)
                            / 1e9
                        )
                        * value
                    )
                else:
                    aggregate = (
                        spec.state_transition * aggregate + spec.state_input_gain * value
                    )
            aggregates.append(aggregate)
        rows.append(tuple(aggregates))
    expected = ridge_oracle(
        tuple(rows), tuple(r.response for r in dataset.rows), spec.ridge_penalty
    )
    assert (model.intercept, *model.coefficients) == pytest.approx(expected, abs=2e-10)
