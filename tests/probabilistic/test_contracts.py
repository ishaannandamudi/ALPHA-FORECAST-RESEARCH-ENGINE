"""Closed non-executable families, explicit conventions and finite immutable payloads."""

from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from afre.probabilistic import (
    DistributionFamily as F,
)
from afre.probabilistic import (
    DistributionParameters,
    ObservationPolicy,
    ProbabilisticBounds,
    ProbabilisticEvaluationProtocol,
    ProbabilityScore,
    QuantileDefinition,
    QuantileInterval,
    QuantileValue,
    ResidualCentering,
    ScalePolicy,
    ScaleSpec,
    ScoreName,
    ScoreState,
    ThresholdComparison,
    ThresholdDefinition,
    ThresholdProbability,
    ThresholdRequest,
)
from afre.probabilistic import (
    DistributionState as S,
)
from afre.probabilistic.distributions import cdf, conditional_variance, expected_value, survival
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json, deserialize
from tests.probabilistic.conftest import ProbabilityCase


@pytest.mark.parametrize(
    "build",
    [
        lambda: QuantileDefinition(()),
        lambda: QuantileDefinition((0.1, 0.9)),
        lambda: QuantileDefinition((0.5, 0.5)),
        lambda: QuantileDefinition((0.0, 0.5)),
        lambda: QuantileDefinition((0.5, 1.0)),
        lambda: QuantileDefinition((float("nan"), 0.5)),
        lambda: ScaleSpec(ScalePolicy.FIXED_SCALE),
        lambda: ScaleSpec(ScalePolicy.FIXED_SCALE, 0.0),
        lambda: ScaleSpec(ScalePolicy.TRAIN_RESIDUAL_STD, 1.0),
        lambda: ScaleSpec(ScalePolicy.TRAIN_RESIDUAL_MAD_SCALED, mad_consistency_factor=0.0),
        lambda: ThresholdProbability(ThresholdRequest(0.0, ThresholdComparison.GT), 1.1),
        lambda: ThresholdProbability(ThresholdRequest(0.0, ThresholdComparison.GT), -0.1),
        lambda: ThresholdDefinition((ThresholdRequest(0.0, ThresholdComparison.GT),) * 2),
        lambda: QuantileInterval(0.9, 0.1),
        lambda: QuantileInterval(0.0, 0.9),
        lambda: ProbabilisticEvaluationProtocol(pit_bins=0),
        lambda: ProbabilisticEvaluationProtocol(pit_bins=101),
        lambda: ProbabilisticEvaluationProtocol((QuantileInterval(0.1, 0.9),) * 2),
        lambda: DistributionParameters(F.GAUSSIAN_LOCATION_SCALE, 0.0, 0.0),
        lambda: DistributionParameters(F.GAUSSIAN_LOCATION_SCALE, 0.0, 1.0, (1.0,)),
        lambda: DistributionParameters(F.EMPIRICAL_RESIDUAL, 0.0, 1.0),
        lambda: DistributionParameters(F.EMPIRICAL_RESIDUAL, 0.0, 0.0, (1.0,)),
        lambda: DistributionParameters(
            F.EMPIRICAL_RESIDUAL, 0.0, 1.0, (1.0, 2.0), state=S.DEGENERATE
        ),
        lambda: DistributionParameters(
            F.QUANTILE_SET,
            0.0,
            1.0,
            quantile_values=(QuantileValue(0.1, 1.0), QuantileValue(0.5, 0.0)),
        ),
        lambda: DistributionParameters(
            F.QUANTILE_SET, 0.0, 1.0, quantile_values=(QuantileValue(0.5, 0.0),) * 2
        ),
        lambda: DistributionParameters(
            F.QUANTILE_SET, 0.0, 1.0, quantile_values=(QuantileValue(0.1, 0.0),)
        ),
        lambda: ProbabilityScore(ScoreName.CRPS, 1.0, ScoreState.UNSUPPORTED, 1),
        lambda: ProbabilityScore(ScoreName.CRPS, None, ScoreState.AVAILABLE, 1),
        lambda: ProbabilityScore(ScoreName.CRPS, 1.0, ScoreState.AVAILABLE, -1),
        lambda: ProbabilityScore(ScoreName.PINBALL, 1.0, ScoreState.AVAILABLE, 1, 0.0),
        lambda: ProbabilityScore(
            ScoreName.INTERVAL_WIDTH, 1.0, ScoreState.AVAILABLE, 1, 0.9, 0.1
        ),
    ],
)
def test_invalid_closed_contracts(build: Callable[[], Artifact]) -> None:
    with pytest.raises(ContractError):
        build()


@pytest.mark.parametrize(
    "changes",
    [
        {"observations": 0},
        {"audit_depth": 65},
        {"serialized_bytes": 16 * 1024 * 1024 + 1},
        {"quantiles": 257},
        {"thresholds": 257},
        {"work_cells": 0},
    ],
)
def test_resource_contracts(changes: dict[str, int]) -> None:
    with pytest.raises(ContractError):
        ProbabilisticBounds(**changes)


def test_safe_roundtrip_and_quantile_only_limits() -> None:
    q = DistributionParameters(
        F.QUANTILE_SET,
        0.0,
        1.0,
        quantile_values=(
            QuantileValue(0.1, -1.0),
            QuantileValue(0.5, 0.0),
            QuantileValue(0.9, 1.0),
        ),
    )
    assert deserialize(canonical_json(q)) == q
    assert expected_value(q) is None and conditional_variance(q) is None
    for fn in (cdf, survival):
        with pytest.raises(ContractError, match="unsupported"):
            fn(q, 0.0)
    with pytest.raises(ContractError):
        replace(q, location=float("inf"))
    with pytest.raises(ContractError):
        replace(q, family=cast(F, "student_t"))


@pytest.mark.parametrize(
    "changes",
    [
        {"random_seed": -1},
        {"random_seed": 2**64},
        {"family": F.QUANTILE_SET},
        {"scale": ScaleSpec(ScalePolicy.FIXED_SCALE, 0.1)},
        {
            "observation_policy": ObservationPolicy.TRAIN_TARGETS,
            "residual_centering": ResidualCentering.CENTER_MEAN,
        },
    ],
)
def test_spec_invalid_assumptions(
    probability_case: ProbabilityCase, changes: dict[str, object]
) -> None:
    constructor = replace
    with pytest.raises(ContractError):
        constructor(probability_case.residual_spec, **changes)


def test_assumptions_change_identity(probability_case: ProbabilityCase) -> None:
    spec = probability_case.residual_spec
    assert (
        replace(spec, residual_centering=ResidualCentering.CENTER_MEAN).fingerprint
        != spec.fingerprint
    )
    assert replace(spec, random_seed=1).fingerprint != spec.fingerprint
    assert (
        replace(spec, quantiles=QuantileDefinition((0.2, 0.5, 0.8))).fingerprint
        != spec.fingerprint
    )
    assert QuantileDefinition((0.9, 0.5, 0.1)) == spec.quantiles
