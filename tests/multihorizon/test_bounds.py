"""Reduced caller bounds reject work and storage before publishing partial results."""

from dataclasses import replace

import pytest

from afre.multihorizon import MultiHorizonBounds
from afre.schema import ContractError
from examples.multihorizon_demo import backbone_spec
from tests.multihorizon.conftest import Case


@pytest.mark.parametrize("policy", ["samples", "work_cells", "features"])
def test_shared_fit_work_bounds(case: Case, policy: str) -> None:
    if policy == "features":
        # One feature is the minimum positive bound; limit dense work instead.
        bounds = replace(MultiHorizonBounds(), features=1, work_cells=1)
    elif policy == "samples":
        bounds = replace(MultiHorizonBounds(), samples=1)
    else:
        bounds = replace(MultiHorizonBounds(), work_cells=1)
    case.repo.multihorizon_bounds = bounds
    before = case.repo._connection.execute("SELECT count(*) FROM mh_artifacts").fetchone()[0]
    with pytest.raises(ContractError, match="bound"):
        case.engine.fit(backbone_spec(case.fixture), 55, 55, 55)
    assert (
        case.repo._connection.execute("SELECT count(*) FROM mh_artifacts").fetchone()[0]
        == before
    )


def test_dependence_work_bound(case: Case) -> None:
    case.repo.multihorizon_bounds = replace(MultiHorizonBounds(), work_cells=1)
    with pytest.raises(ContractError, match="bound"):
        case.engine.fit_dependence(case.fixture.run.fingerprint, 40, 55)


@pytest.mark.parametrize(
    "kind", ["forecasts", "evaluations", "audit_depth", "serialized_bytes"]
)
def test_result_and_audit_bounds(case: Case, kind: str) -> None:
    bundle = case.fixture.bundles[0]
    if kind == "forecasts":
        case.repo.multihorizon_bounds = replace(MultiHorizonBounds(), forecasts=1)
        with pytest.raises(ContractError, match="bound"):
            case.engine.build_bundle(bundle.fit_run_id, bundle.origin, bundle.entries, 61)
    elif kind == "evaluations":
        case.repo.multihorizon_bounds = replace(MultiHorizonBounds(), evaluations=1)
        case.engine.evaluate((bundle.fingerprint,), 75, 75)
        with pytest.raises(ContractError, match="bound"):
            case.engine.evaluate((bundle.fingerprint,), 80, 80)
    elif kind == "audit_depth":
        case.repo.multihorizon_bounds = replace(MultiHorizonBounds(), audit_depth=1)
        with pytest.raises(ContractError, match="bound"):
            case.engine.lineage_audit(bundle.fingerprint)
    else:
        case.repo.multihorizon_bounds = replace(MultiHorizonBounds(), serialized_bytes=100)
        with pytest.raises(ContractError, match="byte"):
            case.engine.lineage_audit(bundle.fingerprint)
