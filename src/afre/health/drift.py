"""Descriptive population moments, Type7 quantiles and exact empirical KS."""

from math import fsum, hypot, sqrt
from statistics import fmean, pstdev

from afre.health.definitions import HealthDiagnosticRequest
from afre.health.schema import HealthDiagnostic as D
from afre.invariance.distributions import empirical_ks
from afre.research_datasets.preprocessing import quantile


def distribution_pair(
    request: HealthDiagnosticRequest, left: tuple[float, ...], right: tuple[float, ...]
) -> tuple[float | None, float | None]:
    kind = request.kind
    if kind in (D.INPUT_KS, D.PREDICTION_KS):
        return 0.0, empirical_ks(left, right)
    if kind is D.STANDARDIZED_MEAN:
        scale = hypot(pstdev(left), pstdev(right)) / sqrt(2)
        return 0.0, (fmean(right) - fmean(left)) / scale if scale > request.tolerance else None
    if kind is D.MEAN_ABSOLUTE_SHIFT:
        return 0.0, abs(fmean(right) - fmean(left))
    if kind in (D.INPUT_STD, D.PREDICTION_STD):
        return pstdev(left), pstdev(right)
    if kind in (D.INPUT_QUANTILE, D.PREDICTION_QUANTILE, D.ERROR_QUANTILE):
        return quantile(left, request.quantile_level), quantile(right, request.quantile_level)
    if kind is D.SIGN_FRACTION:
        return sum(x > 0 for x in left) / len(left), sum(x > 0 for x in right) / len(right)
    return fsum(left) / len(left), fsum(right) / len(right)
