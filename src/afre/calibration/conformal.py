"""Exact finite-sample absolute-residual split conformal, including rolling sets."""

from fractions import Fraction
from math import ceil

from afre.calibration.artifacts import (
    CalibrationObservationSet,
    ConformalScoreSet,
    NonconformityScore,
)
from afre.calibration.definitions import CalibrationSpec
from afre.schema import require
from afre.statistical_models.linear_algebra import finite


def conformal_rank(count: int, alpha: float) -> int:
    require(type(count) is int and count > 0 and 0 < finite(alpha) < 1, "conformal domain")
    # Decimal alpha is the declared convention: avoid binary roundoff at integer ranks.
    rank = ceil((count + 1) * (1 - Fraction(str(alpha))))
    require(rank <= count, "insufficient scores for finite conformal rank")
    return rank


def scores_for(
    spec: CalibrationSpec, observations: CalibrationObservationSet
) -> ConformalScoreSet:
    require(spec.miscoverage_alpha is not None, "conformal alpha missing")
    assert spec.miscoverage_alpha is not None
    scores = tuple(
        sorted(
            (
                NonconformityScore(abs(finite(r.truth - r.median)), r.fingerprint)
                for r in observations.rows
            ),
            key=lambda s: (s.value, s.observation_id),
        )
    )
    rank = conformal_rank(len(scores), spec.miscoverage_alpha)
    return ConformalScoreSet(
        spec.fingerprint,
        observations.fingerprint,
        spec.miscoverage_alpha,
        rank,
        scores[rank - 1].value,
        scores,
    )
