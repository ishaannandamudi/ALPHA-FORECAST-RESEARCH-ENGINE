"""Independent expected splits, ties, leaf means and bounded work."""

from dataclasses import replace

import pytest

from afre.nonlinear import NonlinearBounds, TreeParameters
from afre.nonlinear.trees import fit_tree, thresholds, tree_prediction
from afre.schema import ContractError

SAMPLES = tuple("afre.r_sample:1.0:" + f"{i:064x}" for i in range(1, 7))


def test_known_split() -> None:
    rows = tuple((float(i),) for i in range(6))
    nodes = fit_tree(
        ("x",),
        rows,
        (1.0, 1.0, 1.0, 5.0, 5.0, 5.0),
        SAMPLES,
        TreeParameters(1, 2, 32),
        NonlinearBounds(),
    )
    assert len(nodes) == 3 and nodes[0].threshold == 2.5
    assert nodes[1].value == 1.0 and nodes[2].value == 5.0
    assert nodes[1].sample_ids == SAMPLES[:3]
    value, path = tree_prediction(nodes, ("x",), (2.5,))
    assert value == 1.0 and path[0].branch == "left-leq" and path[-1].branch == "leaf"
    assert tree_prediction(nodes, ("x",), (3.0,))[0] == 5.0


def test_tie_feature_identity() -> None:
    rows = tuple((float(i), float(i)) for i in range(6))
    nodes = fit_tree(
        ("z", "a"),
        rows,
        (0.0, 0.0, 0.0, 2.0, 2.0, 2.0),
        SAMPLES,
        TreeParameters(1, 1),
        NonlinearBounds(),
    )
    assert nodes[0].feature_id == "a" and nodes[0].threshold == 2.5


def test_tie_threshold() -> None:
    nodes = fit_tree(
        ("x",),
        ((0.0,), (1.0,), (2.0,)),
        (0.0, 1.0, 0.0),
        SAMPLES[:3],
        TreeParameters(1, 1),
        NonlinearBounds(),
    )
    assert nodes[0].threshold == 0.5


@pytest.mark.parametrize("depth", [1, 2, 3, 4])
def test_depth(depth: int) -> None:
    nodes = fit_tree(
        ("x",),
        tuple((float(i),) for i in range(6)),
        tuple(float(i) for i in range(6)),
        SAMPLES,
        TreeParameters(depth, 1),
        NonlinearBounds(),
    )
    assert max(n.depth for n in nodes) <= depth
    assert all(n.sample_ids for n in nodes)


def test_leaf_count_and_constant() -> None:
    for minimum, response in ((4, (0.0, 1.0, 2.0, 3.0, 4.0, 5.0)), (1, (1.0,) * 6)):
        nodes = fit_tree(
            ("x",),
            tuple((float(i),) for i in range(6)),
            response,
            SAMPLES,
            TreeParameters(4, minimum),
            NonlinearBounds(),
        )
        assert len(nodes) == 1


def test_bounded_candidates() -> None:
    assert thresholds(tuple(float(i) for i in range(100)), 3) == (0.5, 49.5, 98.5)
    assert thresholds(tuple(float(i) for i in range(100)), 1) == (49.5,)
    assert thresholds((1.0, 1.0), 3) == ()
    assert thresholds((1.0, 2.0), 3) == (1.5,)


def test_split_work_bound() -> None:
    with pytest.raises(ContractError, match="work bound"):
        fit_tree(
            ("x",),
            tuple((float(i),) for i in range(6)),
            tuple(float(i) for i in range(6)),
            SAMPLES,
            TreeParameters(2, 1),
            replace(NonlinearBounds(), work_cells=1),
        )
    with pytest.raises(ContractError, match="depth"):
        fit_tree(
            ("x",),
            ((0.0,), (1.0,)),
            (0.0, 1.0),
            SAMPLES[:2],
            TreeParameters(2, 1),
            replace(NonlinearBounds(), tree_depth=1),
        )


def test_improvement_and_corrupt_child() -> None:
    nodes = fit_tree(
        ("x",),
        tuple((float(i),) for i in range(6)),
        tuple(float(i) for i in range(6)),
        SAMPLES,
        TreeParameters(1, 1, minimum_improvement=100.0),
        NonlinearBounds(),
    )
    assert len(nodes) == 1
    split = fit_tree(
        ("x",),
        tuple((float(i),) for i in range(6)),
        (0.0,) * 3 + (1.0,) * 3,
        SAMPLES,
        TreeParameters(1, 1),
        NonlinearBounds(),
    )
    with pytest.raises(ContractError, match="child"):
        tree_prediction((replace(split[0], right=100), *split[1:]), ("x",), (5.0,))
