"""Independent numerical identities for synthetic health diagnostics."""

from math import sqrt
from statistics import fmean

from afre.health import HealthDiagnostic as D
from afre.health import HealthDiagnosticRequest, HealthObservation
from afre.health.drift import distribution_pair
from afre.health.vectors import vector_pair
from afre.ids import InstrumentId


def numerical_errors() -> tuple[tuple[str, float], ...]:
    a, b = (1.0, 2.0, 3.0), (4.0, 5.0, 6.0)
    expected = {
        D.INPUT_MEAN: (2.0, 5.0),
        D.INPUT_STD: (sqrt(2 / 3), sqrt(2 / 3)),
        D.INPUT_QUANTILE: (2.0, 5.0),
        D.INPUT_KS: (0.0, 1.0),
        D.STANDARDIZED_MEAN: (0.0, 3 / sqrt(2 / 3)),
        D.MEAN_ABSOLUTE_SHIFT: (0.0, 3.0),
    }
    errors = []
    for kind, (left, right) in expected.items():
        actual = distribution_pair(HealthDiagnosticRequest(kind, "input", 1), a, b)
        assert all(v is not None for v in actual)
        errors.append(
            (
                kind.value,
                max(abs(float(actual[0] or 0) - left), abs(float(actual[1] or 0) - right)),
            )
        )
    identity = InstrumentId("health-oracle", "1").fingerprint

    def row(values: tuple[float, ...]) -> HealthObservation:
        return HealthObservation(
            identity,
            identity,
            0,
            0,
            tuple(("parameter:" + str(i), v) for i, v in enumerate(values)),
            "explicit-oracle",
            (),
            constructed_ns=0,
        )

    x, y = (1.0, 2.0, -3.0), (-1.0, 4.0, -3.0)
    mx, my = fmean(x), fmean(y)
    correlation = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / sqrt(
        sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y)
    )
    for kind, value in (
        (D.PARAMETER_L1, 4 / 6),
        (D.PARAMETER_L2, sqrt(8 / 14)),
        (D.PARAMETER_CORRELATION, correlation),
        (D.PARAMETER_SIGN_CHANGES, 1.0),
    ):
        _, vector_value, _ = vector_pair(
            HealthDiagnosticRequest(kind, "parameter", 1), (row(x),), (row(y),)
        )
        assert vector_value is not None
        errors.append((kind.value, abs(vector_value - value)))
    assert max(v for _, v in errors) < 1e-12
    return tuple(errors)
