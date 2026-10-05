"""Dimension, count, payload and graph limits reject oversized research artifacts."""

from dataclasses import replace

import pytest

from afre.mixture import MixtureForecast
from afre.schema import ContractError
from tests.mixture.conftest import Case


@pytest.mark.parametrize(
    "bound",
    [
        "experts",
        "components",
        "training_samples",
        "forecasts",
        "evaluations",
        "audit_nodes",
        "audit_depth",
        "serialized_bytes",
        "work_cells",
    ],
)
def test_actual_overflow(case: Case, bound: str) -> None:
    if bound == "evaluations":
        case.engine.evaluate(case.fixture.forecast_ids, 100, 100)
    case.repo.mixture_bounds = replace(
        case.repo.mixture_bounds, **{bound: 1 if bound != "serialized_bytes" else 20}
    )
    with pytest.raises(ContractError, match="bound|count"):
        if bound in ("experts", "serialized_bytes"):
            case.engine.forecast(case.forecast.request)
        elif bound == "components":
            case.repo.get(MixtureForecast, case.fixture.probability_ids[0])
        elif bound in ("training_samples", "work_cells"):
            case.engine.fit(case.fixture.learned_spec, case.fixture.training_ids, 40, 40, 40)
        elif bound == "forecasts":
            case.engine.evaluate(case.fixture.forecast_ids, 100, 100)
        elif bound == "evaluations":
            case.engine.evaluate(case.fixture.forecast_ids, 101, 101)
        else:
            case.engine.audit_lineage(case.forecast.fingerprint)
