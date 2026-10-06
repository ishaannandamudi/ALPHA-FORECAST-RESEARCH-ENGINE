"""Explicit count, byte, tree-work and unified-lineage bounds."""

from dataclasses import replace

import pytest

from afre.nonlinear import InteractionSet, NonlinearBounds, NonlinearRepository, TreeParameters
from afre.nonlinear.bounds import check_nonlinear_bounds
from afre.nonlinear.lineage import lineage_for
from afre.schema import Artifact, ContractError
from tests.nonlinear.conftest import Case


@pytest.mark.parametrize(
    "field",
    [
        "interactions",
        "features",
        "training_rows",
        "split_candidates",
        "tree_depth",
        "work_cells",
        "artifacts",
        "evaluations",
        "audit_nodes",
        "audit_depth",
        "serialized_bytes",
    ],
)
def test_positive_bounds(field: str) -> None:
    with pytest.raises(ContractError):
        replace(NonlinearBounds(), **{field: 0})


@pytest.mark.parametrize(
    "field",
    [
        "interactions",
        "features",
        "split_candidates",
        "tree_depth",
        "audit_depth",
        "serialized_bytes",
    ],
)
def test_hard_bounds(field: str) -> None:
    bounds = NonlinearBounds()
    with pytest.raises(ContractError):
        replace(bounds, **{field: getattr(bounds, field) + 1_000_000_000})


@pytest.mark.parametrize("maximum", [0, 5])
def test_tree_depth_contract(maximum: int) -> None:
    with pytest.raises(ContractError):
        TreeParameters(maximum_depth=maximum)


@pytest.mark.parametrize(
    "kind", ["set", "spec", "input", "matrix", "model", "tree", "forecast", "bytes"]
)
def test_payload_and_work_bounds(case: Case, kind: str) -> None:
    bounds = NonlinearBounds()
    value: Artifact
    if kind in ("set", "spec"):
        value = (
            case.fixture.specs[0].interaction_set if kind == "set" else case.fixture.specs[0]
        )
        bounds = replace(bounds, interactions=1)
    elif kind == "input":
        value = case.inputs
        bounds = replace(bounds, features=1)
    elif kind == "matrix":
        value = case.repo.get_any(case.fixture.models[0].matrix_id)
        bounds = replace(bounds, work_cells=1)
    elif kind in ("model", "tree"):
        value = case.fixture.models[0 if kind == "model" else 2]
        bounds = (
            replace(bounds, features=1) if kind == "model" else replace(bounds, tree_depth=1)
        )
    elif kind == "forecast":
        value = case.forecast
        bounds = replace(bounds, interactions=1)
    else:
        value = case.forecast
        bounds = replace(bounds, serialized_bytes=1)
    with pytest.raises(ContractError, match="bound"):
        check_nonlinear_bounds(value, bounds)


@pytest.mark.parametrize("field", ["audit_nodes", "audit_depth", "serialized_bytes"])
def test_unified_lineage_bound(case: Case, field: str) -> None:
    with (
        NonlinearRepository(case.path, replace(NonlinearBounds(), **{field: 1})) as bounded,
        pytest.raises(ContractError, match="bound"),
    ):
        lineage_for(bounded, case.forecast.fingerprint)


def test_empty_and_duplicate_input_bound(case: Case) -> None:
    spec = case.fixture.specs[0]
    for ids in ((), (case.fixture.train_ids[0],) * 2):
        with pytest.raises(ContractError):
            case.engine.matrix(spec, ids, case.fixture.models[0].transform_ids, 40)
    with pytest.raises(ContractError):
        InteractionSet(spec.interaction_set.definitions, spec.target, maximum_count=1)
    with pytest.raises(ContractError):
        case.engine.input(case.inputs.sample_id, ())
