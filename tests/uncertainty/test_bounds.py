"""Caller bounds, strict closed contracts and lineage limits fail before publication."""

from dataclasses import fields, replace

import pytest

from afre.schema import ContractError
from afre.uncertainty import (
    UncertaintyBounds,
    UncertaintyEvaluationSpec,
    UncertaintyRepository,
    UncertaintyRequest,
    UncertaintySpec,
    UncertaintyType,
)
from tests.uncertainty.conftest import Case


@pytest.mark.parametrize("name", [f.name for f in fields(UncertaintyBounds)])
def test_bound_hard_limits(name: str) -> None:
    b = UncertaintyBounds()
    with pytest.raises(ContractError):
        replace(b, **{name: 0})
    with pytest.raises(ContractError):
        replace(b, **{name: getattr(b, name) + 1})


@pytest.mark.parametrize(
    "limit",
    [
        "components",
        "samples",
        "dimensions",
        "experts",
        "buckets",
        "cohorts",
        "serialized_bytes",
        "audit_nodes",
        "audit_depth",
        "artifacts",
    ],
)
def test_repository_resource_limits(case: Case, limit: str) -> None:
    path = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with (
        UncertaintyRepository(path, replace(UncertaintyBounds(), **{limit: 1})) as limited,
        pytest.raises(ContractError),
    ):
        if limit in ("audit_nodes", "audit_depth"):
            from afre.uncertainty import UncertaintyEngine

            UncertaintyEngine(limited).audit_lineage(case.result().fingerprint)
        elif limit in ("samples", "buckets", "cohorts"):
            from afre.uncertainty import UncertaintyEngine

            UncertaintyEngine(limited).evaluate(
                case.fixture.results("gaussian"), UncertaintyEvaluationSpec(), 100, 100
            )
        elif limit == "dimensions":
            limited.get_any(case.fixture.covariances[0].fingerprint)
        elif limit == "experts":
            from afre.uncertainty.sources import source_for

            source_for(limited, case.result("mixture").forecast_id)
        elif limit == "artifacts":
            with limited.transaction():
                limited.put(UncertaintyRequest(UncertaintyType.DATA_QUALITY))
        else:
            limited.get_any(case.result().spec_id)


@pytest.mark.parametrize(
    "kind",
    [
        "duplicate",
        "total",
        "levels",
        "count",
        "tolerance",
        "seed",
        "calibration",
        "implementation",
    ],
)
def test_invalid_spec(case: Case, kind: str) -> None:
    old = case.repo.get(UncertaintySpec, case.result().spec_id)
    with pytest.raises(ContractError):
        if kind == "duplicate":
            replace(old, requests=(old.requests[0], old.requests[0]))
        elif kind == "total":
            replace(old, requests=(UncertaintyRequest(UncertaintyType.PARAMETER),))
        elif kind == "levels":
            replace(old, interval_levels=(0.9, 0.1))
        elif kind == "count":
            replace(old, minimum_count=1)
        elif kind == "tolerance":
            replace(old, tolerance=0.0)
        elif kind == "seed":
            replace(old, seed=-1)
        elif kind == "calibration":
            replace(old, calibration_policy="fit-test")
        else:
            replace(old, implementation_version="unknown")
