"""Cartesian product, predeclared identity and admission before any fit."""

from dataclasses import replace
from itertools import product

import pytest

from afre.schema import ContractError
from afre.selection import (
    DiscreteDimension,
    NativeCandidateRecipe,
    ResourceBudget,
    SelectionBounds,
    SelectionEngine,
    enumerate_candidates,
)
from afre.statistical_models.definitions import BaselineModelSpec
from tests.selection.conftest import SelectionCase


def grid(case: SelectionCase) -> tuple[NativeCandidateRecipe, ...]:
    spec = case.space.recipes[0].native_spec
    assert isinstance(spec, BaselineModelSpec)
    return tuple(
        replace(
            case.space.recipes[0],
            native_spec=replace(spec, random_seed=seed, max_iterations=iterations),
            choices=(("iterations", str(iterations)), ("seed", str(seed))),
        )
        for seed, iterations in product((0, 1), (10, 20))
    )


def test_cartesian_oracle_order_and_identity(case: SelectionCase) -> None:
    recipes = grid(case)
    space = replace(
        case.space,
        dimensions=(
            DiscreteDimension("seed", ("1", "0")),
            DiscreteDimension("iterations", ("20", "10")),
        ),
        recipes=recipes,
    )
    assert {c.recipe.choices for c in enumerate_candidates(space)} == {
        (("iterations", str(i)), ("seed", str(s))) for s in (0, 1) for i in (10, 20)
    }
    reversed_space = replace(
        space,
        dimensions=tuple(
            replace(d, values=tuple(reversed(d.values))) for d in reversed(space.dimensions)
        ),
        recipes=tuple(reversed(recipes)),
        validation_sample_ids=tuple(reversed(space.validation_sample_ids)),
    )
    assert reversed_space == space
    assert enumerate_candidates(reversed_space) == enumerate_candidates(space)
    assert len({c.fingerprint for c in enumerate_candidates(space)}) == 4


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_candidates", 0),
        ("max_fit_operations", 0),
        ("max_train_rows", 0),
        ("max_validation_rows", 0),
        ("max_numerical_iterations", 0),
        ("max_payload_bytes", 0),
        ("max_candidates", 129),
        ("max_payload_bytes", 8388609),
    ],
)
def test_absolute_budget_bounds(field: str, value: int) -> None:
    with pytest.raises(ContractError):
        replace(ResourceBudget(128, 4096, 256000, 256000, 100000000, 8388608), **{field: value})


@pytest.mark.parametrize(
    "field",
    (
        "candidates",
        "dimensions",
        "rows",
        "comparisons",
        "artifacts",
        "payload_bytes",
        "snapshot_bytes",
        "publication_rows",
        "lineage_nodes",
        "lineage_depth",
    ),
)
def test_bounds_reject_zero(field: str) -> None:
    with pytest.raises(ContractError):
        replace(SelectionBounds(), **{field: 0})


@pytest.mark.parametrize(
    "kind",
    (
        "duplicate-dimension",
        "missing-product",
        "oversized",
        "duplicate-value",
        "unknown-baseline",
    ),
)
def test_invalid_grid_rejected(case: SelectionCase, kind: str) -> None:
    with pytest.raises(ContractError):
        if kind == "duplicate-dimension":
            replace(case.space, dimensions=case.space.dimensions * 2)
        elif kind == "missing-product":
            replace(case.space, recipes=case.space.recipes[:1])
        elif kind == "oversized":
            replace(case.space, budget=replace(case.space.budget, max_candidates=1))
        elif kind == "duplicate-value":
            DiscreteDimension("x", ("a", "a"))
        else:
            replace(case.space, baseline_recipe_id=case.result.fingerprint)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_fit_operations", 1),
        ("max_train_rows", 1),
        ("max_validation_rows", 1),
        ("max_numerical_iterations", 1),
        ("max_payload_bytes", 1),
    ],
)
def test_budget_rejected_atomically_before_fit(
    case: SelectionCase, field: str, value: int
) -> None:
    old = tuple(case.repository._connection.execute("SELECT fingerprint FROM sel_artifacts"))
    space = replace(case.space, budget=replace(case.space.budget, **{field: value}))
    with pytest.raises(ContractError, match="budget"):
        SelectionEngine(case.repository).select(space, 100, 100)
    assert (
        tuple(case.repository._connection.execute("SELECT fingerprint FROM sel_artifacts"))
        == old
    )
