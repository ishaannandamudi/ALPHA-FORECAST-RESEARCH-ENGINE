"""Independent point/probability oracles and explicit unavailable/tie protocols."""

import math
from dataclasses import replace

import pytest

from afre.hashing import bytes_digest
from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.schema import DistributionFamily
from afre.schema import ContractError
from afre.selection.criteria import loss, metric
from afre.selection.decisions import ordering_for, winner_for
from afre.selection.results import CandidateValidationPair, CandidateValidationResult
from afre.selection.schema import CandidateStatus, SelectionCriterion, SelectionStatus
from tests.selection.conftest import SelectionCase


def identity(domain: str, n: int) -> str:
    return f"afre.{domain}:1.0:{bytes_digest(str(n).encode())}"


def pairs(
    predictions: tuple[float, ...], truths: tuple[float, ...]
) -> tuple[CandidateValidationPair, ...]:
    return tuple(
        CandidateValidationPair(
            identity("r_sample", i),
            identity("target_vintage", i),
            identity("m_prediction", i),
            p,
            y,
            None,
        )
        for i, (p, y) in enumerate(zip(predictions, truths, strict=True))
    )


@pytest.mark.parametrize(
    "criterion,expected",
    [
        (SelectionCriterion.MIN_MSE, 11 / 3),
        (SelectionCriterion.MIN_MAE, 5 / 3),
        (SelectionCriterion.MAX_R2, -5 / 6),
    ],
)
def test_independent_point_metrics(criterion: SelectionCriterion, expected: float) -> None:
    rows = pairs((0.0, 2.0, 1.0), (1.0, 1.0, 4.0))
    assert metric(
        criterion, rows, tuple(loss(criterion, p.prediction, p.truth, None) for p in rows)
    ) == pytest.approx(expected, abs=1e-15)


@pytest.mark.parametrize("criterion", tuple(SelectionCriterion))
def test_empty_is_unavailable(criterion: SelectionCriterion) -> None:
    assert metric(criterion, (), ()) is None


def test_constant_target_r2_unavailable() -> None:
    assert metric(SelectionCriterion.MAX_R2, pairs((1.0, 2.0), (3.0, 3.0)), (4.0, 1.0)) is None


@pytest.mark.parametrize("scale,truth", [(0.5, -0.7), (1.0, 0.0), (2.0, 3.0)])
def test_gaussian_quadrature_crps_and_density_nll(scale: float, truth: float) -> None:
    law = DistributionParameters(DistributionFamily.GAUSSIAN_LOCATION_SCALE, 0.0, scale)

    # Independent integral of (CDF - empirical indicator)^2, split at truth.
    def integral(a: float, b: float, right: bool) -> float:
        n = 10000
        step = (b - a) / n
        terms = []
        for i in range(n + 1):
            x = a + i * step
            cdf = 0.5 * (1 + math.erf(x / (scale * math.sqrt(2))))
            terms.append((1 if i in (0, n) else 4 if i % 2 else 2) * (cdf - float(right)) ** 2)
        return math.fsum(terms) * step / 3

    expected = integral(-12 * scale, truth, False) + integral(truth, 12 * scale, True)
    assert loss(SelectionCriterion.MIN_CRPS, 0.0, truth, law) == pytest.approx(
        expected, abs=1e-10
    )
    density = math.exp(-0.5 * (truth / scale) ** 2) / (scale * math.sqrt(2 * math.pi))
    assert loss(SelectionCriterion.MIN_NLL, 0.0, truth, law) == pytest.approx(
        -math.log(density), abs=1e-14
    )


def test_empirical_pairwise_crps_oracle_and_unavailable_nll() -> None:
    samples = (-1.0, 0.2, 2.0)
    law = DistributionParameters(DistributionFamily.EMPIRICAL_RESIDUAL, 0.3, 1.0, samples)
    atoms = tuple(0.3 + s for s in samples)
    truth = 0.8
    expected = (
        math.fsum(abs(x - truth) for x in atoms) / 3
        - math.fsum(abs(x - y) for x in atoms for y in atoms) / 18
    )
    assert loss(SelectionCriterion.MIN_CRPS, 0.3, truth, law) == pytest.approx(
        expected, abs=1e-15
    )
    assert loss(SelectionCriterion.MIN_NLL, 0.3, truth, law) is None
    assert loss(SelectionCriterion.MIN_CRPS, 0.0, truth, None) is None
    assert loss(SelectionCriterion.MIN_NLL, 0.0, truth, None) is None


def validation(
    n: int, value: float | None, secondary: float | None = None
) -> CandidateValidationResult:
    rows = pairs((1.0, 2.0), (2.0, 4.0)) if value is not None else ()
    samples = tuple(p.sample_id for p in pairs((1.0, 2.0), (2.0, 4.0)))
    return CandidateValidationResult(
        identity("sel_candidate", n),
        identity("sel_fit", n),
        SelectionCriterion.MIN_MSE,
        value,
        secondary,
        CandidateStatus.VALID if value is not None else CandidateStatus.INCOMPATIBLE,
        "oracle",
        samples,
        rows,
        () if rows else tuple((i, "incompatible") for i in samples),
        100,
        100,
        identity("mt_trial", n),
    )


def test_fingerprint_tie_all_failures_and_single_policy(case: SelectionCase) -> None:
    rows = (validation(2, 1.0), validation(1, 1.0), validation(3, None))
    expected = tuple(sorted(r.candidate_id for r in rows[:2])) + (rows[2].candidate_id,)
    assert ordering_for(case.space, rows) == expected
    assert winner_for(case.space, rows) == (expected[0], SelectionStatus.COMPETITIVE)
    assert winner_for(case.space, (rows[2],)) == (None, SelectionStatus.NO_VALID_CANDIDATE)
    assert winner_for(replace(case.space, permit_single_valid=False), (rows[0],)) == (
        None,
        SelectionStatus.NO_VALID_CANDIDATE,
    )
    assert winner_for(case.space, (rows[0],)) == (
        rows[0].candidate_id,
        SelectionStatus.NONCOMPETITIVE,
    )


def test_secondary_predeclared_lexicographic_maximize(case: SelectionCase) -> None:
    space = replace(case.space, secondary_criterion=SelectionCriterion.MAX_R2)
    rows = (validation(1, 1.0, 0.1), validation(2, 1.0, 0.9))
    assert ordering_for(space, rows)[0] == rows[1].candidate_id
    assert (
        ordering_for(
            replace(
                space,
                criterion=SelectionCriterion.MAX_R2,
                secondary_criterion=SelectionCriterion.MIN_MAE,
            ),
            (validation(1, 0.5, 0.2), validation(2, 0.5, 0.1)),
        )[0]
        == rows[1].candidate_id
    )


def test_different_truth_support_rejects_ranking(case: SelectionCase) -> None:
    a, b = validation(1, 1.0), validation(2, 2.0)
    changed = replace(
        b, pairs=(replace(b.pairs[0], truth_id=identity("target_vintage", 90)), b.pairs[1])
    )
    with pytest.raises(ContractError, match="matched"):
        ordering_for(case.space, (a, changed))
