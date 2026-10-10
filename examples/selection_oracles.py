"""Independent bounded metric oracles, not fitted criteria or optimization advice."""

import math

from afre.hashing import bytes_digest
from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.schema import DistributionFamily
from afre.selection.criteria import loss, metric
from afre.selection.results import CandidateValidationPair
from afre.selection.schema import SelectionCriterion


def numerical_errors() -> dict[str, float]:
    def identity(domain: str, i: int) -> str:
        return f"afre.{domain}:1.0:{bytes_digest(str(i).encode())}"

    predictions = (0.0, 2.0, 1.0)
    truths = (1.0, 1.0, 4.0)
    pairs = tuple(
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
    errors = {}
    for criterion, expected in (
        (SelectionCriterion.MIN_MSE, 11 / 3),
        (SelectionCriterion.MIN_MAE, 5 / 3),
        (SelectionCriterion.MAX_R2, -5 / 6),
    ):
        actual = metric(
            criterion, pairs, tuple(loss(criterion, p.prediction, p.truth, None) for p in pairs)
        )
        assert actual is not None
        errors[criterion.value] = abs(actual - expected)
    law = DistributionParameters(DistributionFamily.GAUSSIAN_LOCATION_SCALE, 0.0, 1.0)
    truth = 0.7
    n = 10000

    def integrate(a: float, b: float, right: bool) -> float:
        step = (b - a) / n
        terms = []
        for i in range(n + 1):
            cdf = 0.5 * (1 + math.erf((a + i * step) / math.sqrt(2)))
            weight = 1 if i in (0, n) else 4 if i % 2 else 2
            terms.append(weight * (cdf - float(right)) ** 2)
        return math.fsum(terms) * step / 3

    crps = loss(SelectionCriterion.MIN_CRPS, 0.0, truth, law)
    nll = loss(SelectionCriterion.MIN_NLL, 0.0, truth, law)
    assert crps is not None and nll is not None
    errors["Gaussian_CRPS_quadrature"] = abs(
        crps - integrate(-12.0, truth, False) - integrate(truth, 12.0, True)
    )
    errors["Gaussian_NLL_density"] = abs(
        nll + math.log(math.exp(-(truth**2) / 2) / math.sqrt(2 * math.pi))
    )
    samples = (-1.0, 0.2, 2.0)
    empirical = DistributionParameters(DistributionFamily.EMPIRICAL_RESIDUAL, 0.3, 1.0, samples)
    atoms = tuple(0.3 + x for x in samples)
    expected = (
        math.fsum(abs(x - truth) for x in atoms) / 3
        - math.fsum(abs(x - y) for x in atoms for y in atoms) / 18
    )
    value = loss(SelectionCriterion.MIN_CRPS, 0.3, truth, empirical)
    assert value is not None
    errors["Empirical_CRPS_pairwise"] = abs(value - expected)
    return errors
