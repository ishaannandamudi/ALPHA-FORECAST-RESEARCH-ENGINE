"""Independent integer timeline fixtures; values are not an implementation oracle."""

from dataclasses import replace

import pytest

from afre.cross_sectional.schema import SignalQuality
from afre.schema import ContractError
from afre.sequence import (
    SequenceCompleteness,
    SequencePadding,
    SequenceRevisionPolicy,
    SequenceTimeEncoding,
    SequenceWindowMode,
    SequenceWindowSpec,
)
from tests.sequence.conftest import Case


def test_latest_fixed_count(case: Case) -> None:
    obs = tuple(case.observe(t, float(t)) for t in (10, 20, 30))
    window = SequenceWindowSpec(SequenceWindowMode.FIXED_OBSERVATION_COUNT, 2)
    snap = case.engine.snapshot(
        case.forecast.origin, (case.micro,), window, 61, tuple(o.fingerprint for o in obs)
    )
    assert snap.observation_times == (20, 30)
    assert snap.values == ((20.0,), (30.0,))
    assert snap.mask == ((True,), (True,))
    assert snap.completeness is SequenceCompleteness.COMPLETE


@pytest.mark.parametrize("lower", [False, True])
@pytest.mark.parametrize("upper", [False, True])
def test_elapsed_boundaries(case: Case, lower: bool, upper: bool) -> None:
    obs = tuple(case.observe(t, float(t)) for t in (39, 40, 41, 60, 61))
    window = SequenceWindowSpec(
        SequenceWindowMode.ELAPSED_DURATION,
        8,
        duration_ns=20,
        lower_inclusive=lower,
        upper_inclusive=upper,
    )
    snap = case.engine.snapshot(
        case.forecast.origin, (case.micro,), window, 61, tuple(o.fingerprint for o in obs)
    )
    assert tuple(t for t in snap.observation_times if t is not None) == (
        *((40,) if lower else ()),
        41,
        *((60,) if upper else ()),
    )


def test_future_availability_and_revision_excluded(case: Case) -> None:
    old = case.observe(20, 2.0)
    known = case.observe(20, 3.0, 50)
    future = case.observe(20, 999.0, 65)
    late = case.observe(30, 1000.0, 70)
    window = SequenceWindowSpec(SequenceWindowMode.FIXED_OBSERVATION_COUNT, 1)
    snap = case.engine.snapshot(
        case.forecast.origin,
        (case.micro,),
        window,
        70,
        tuple(o.fingerprint for o in (future, old, late, known)),
    )
    assert snap.values == ((3.0,),)
    assert snap.observation_ids == ((known.fingerprint,),)
    assert (future.fingerprint, "future-availability") in snap.exclusions
    assert (old.fingerprint, "superseded-available-revision") in snap.exclusions


@pytest.mark.parametrize(
    "policy", [SequenceRevisionPolicy.FAIL_ON_MULTIPLE, SequenceRevisionPolicy.EXACT_VINTAGE]
)
def test_revision_policy(case: Case, policy: SequenceRevisionPolicy) -> None:
    old, correction = case.observe(20, 2.0), case.observe(20, 4.0, 50)
    ids = (old.fingerprint, correction.fingerprint)
    window = SequenceWindowSpec(
        SequenceWindowMode.FIXED_OBSERVATION_COUNT,
        1,
        revision_policy=policy,
        exact_observation_ids=ids if policy is SequenceRevisionPolicy.EXACT_VINTAGE else (),
    )
    with pytest.raises(ContractError, match="multiple semantic"):
        case.engine.snapshot(case.forecast.origin, (case.micro,), window, 60, ids)
    if policy is SequenceRevisionPolicy.EXACT_VINTAGE:
        exact = replace(window, exact_observation_ids=(old.fingerprint,))
        snap = case.engine.snapshot(
            case.forecast.origin, (case.micro,), exact, 60, (old.fingerprint,)
        )
        assert snap.values == ((2.0,),)
        with pytest.raises(ContractError, match="exact vintage candidates"):
            case.engine.snapshot(case.forecast.origin, (case.micro,), exact, 60, ids)


@pytest.mark.parametrize("padding", list(SequencePadding))
def test_padding_and_real_zero(case: Case, padding: SequencePadding) -> None:
    zero = case.observe(20, 0.0)
    window = SequenceWindowSpec(SequenceWindowMode.FIXED_OBSERVATION_COUNT, 3, padding=padding)
    if padding is SequencePadding.FAIL_IF_SHORT:
        with pytest.raises(ContractError, match="FAIL_IF_SHORT"):
            case.engine.snapshot(
                case.forecast.origin, (case.micro,), window, 60, (zero.fingerprint,)
            )
        return
    snap = case.engine.snapshot(
        case.forecast.origin, (case.micro,), window, 60, (zero.fingerprint,)
    )
    expected = (
        ((None,), (None,), (0.0,))
        if padding is SequencePadding.LEFT_PAD_MASKED
        else ((0.0,), (None,), (None,))
    )
    assert snap.values == expected
    assert sum(m for row in snap.mask for m in row) == 1
    assert snap.masked_fraction == pytest.approx(2 / 3)


@pytest.mark.parametrize("encoding", list(SequenceTimeEncoding))
def test_irregular_encoding(case: Case, encoding: SequenceTimeEncoding) -> None:
    obs = tuple(case.observe(t, 1.0) for t in (10, 13, 29))
    window = SequenceWindowSpec(
        SequenceWindowMode.FIXED_OBSERVATION_COUNT, 3, time_encoding=encoding
    )
    snap = case.engine.snapshot(
        case.forecast.origin, (case.micro,), window, 61, tuple(o.fingerprint for o in obs)
    )
    expected = {
        SequenceTimeEncoding.NONE: (0.0, 0.0, 0.0),
        SequenceTimeEncoding.DELTA_SECONDS: (0.0, 3e-9, 16e-9),
        SequenceTimeEncoding.AGE_FROM_ORIGIN: (50e-9, 47e-9, 31e-9),
        SequenceTimeEncoding.NORMALIZED_POSITION: (0.0, 0.5, 1.0),
    }
    assert snap.time_encoding == expected[encoding]
    assert snap.gap_seconds == (3e-9, 16e-9)


@pytest.mark.parametrize(
    "quality", [SignalQuality.MISSING, SignalQuality.STALE, SignalQuality.INVALID]
)
def test_quality_is_masked(case: Case, quality: SignalQuality) -> None:
    missing = case.observe(20, None, quality=quality)
    zero = case.observe(30, 0.0)
    window = SequenceWindowSpec(SequenceWindowMode.FIXED_OBSERVATION_COUNT, 2)
    snap = case.engine.snapshot(
        case.forecast.origin, (case.micro,), window, 60, (missing.fingerprint, zero.fingerprint)
    )
    assert snap.values == ((None,), (0.0,))
    assert snap.mask == ((False,), (True,))
    assert (missing.fingerprint, quality.value + "-source") in snap.exclusions


def test_completeness_insufficient_unavailable(case: Case) -> None:
    obs = case.observe(20, 1.0)
    window = SequenceWindowSpec(
        SequenceWindowMode.FIXED_OBSERVATION_COUNT, 3, minimum_observations=2
    )
    a = case.engine.snapshot(
        case.forecast.origin, (case.micro,), window, 60, (obs.fingerprint,)
    )
    b = case.engine.snapshot(case.forecast.origin, (case.micro,), window, 60, ())
    assert a.completeness is SequenceCompleteness.INSUFFICIENT
    assert b.completeness is SequenceCompleteness.UNAVAILABLE


def test_order_and_latest_equal_time_tie(case: Case) -> None:
    obs = tuple(case.observe(20, value, 50) for value in (1.0, 2.0))
    window = SequenceWindowSpec(SequenceWindowMode.FIXED_OBSERVATION_COUNT, 1)
    ids = tuple(o.fingerprint for o in obs)
    a = case.engine.snapshot(case.forecast.origin, (case.micro,), window, 60, ids)
    b = case.engine.snapshot(
        case.forecast.origin, (case.micro,), window, 60, tuple(reversed(ids))
    )
    assert a == b
    expected = max(obs, key=lambda o: o.revision_id)
    assert a.observation_ids == ((expected.fingerprint,),)
