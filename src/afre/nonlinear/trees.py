"""Depth-limited TRAIN SSE trees with bounded midpoint candidates and exact paths."""

from afre.nonlinear.artifacts import TreeNode, TreePathStep
from afre.nonlinear.definitions import TreeParameters
from afre.nonlinear.schema import NonlinearBounds
from afre.schema import require
from afre.statistical_models.linear_algebra import dot, finite, total


def leaf_statistics(values: tuple[float, ...]) -> tuple[float, float]:
    mean = finite(values[0] + total([finite(v - values[0]) for v in values]) / len(values))
    residual = tuple(finite(v - mean) for v in values)
    return mean, dot(residual, residual)


def thresholds(values: tuple[float, ...], maximum: int) -> tuple[float, ...]:
    unique = sorted(set(values))
    candidates = tuple(
        finite(a / 2 + b / 2)
        for a, b in zip(unique, unique[1:], strict=False)
        if a < finite(a / 2 + b / 2) < b
    )
    if len(candidates) <= maximum:
        return candidates
    # Equal index spacing, including first/last when maximum > 1; no label-based selection.
    indices = (
        tuple(i * (len(candidates) - 1) // (maximum - 1) for i in range(maximum))
        if maximum > 1
        else (len(candidates) // 2,)
    )
    return tuple(candidates[i] for i in indices)


def fit_tree(
    columns: tuple[str, ...],
    rows: tuple[tuple[float, ...], ...],
    response: tuple[float, ...],
    samples: tuple[str, ...],
    parameters: TreeParameters,
    bounds: NonlinearBounds,
) -> tuple[TreeNode, ...]:
    require(
        bool(rows)
        and len(rows) == len(response) == len(samples)
        and all(len(r) == len(columns) for r in rows),
        "tree TRAIN shape",
    )
    require(
        parameters.maximum_depth <= bounds.tree_depth
        and parameters.maximum_candidates <= bounds.split_candidates,
        "tree runtime depth/candidate bound",
    )
    nodes: list[TreeNode] = []
    work = 0

    def build(indices: tuple[int, ...], depth: int) -> int:
        nonlocal work
        node_id = len(nodes)
        mean, error = leaf_statistics(tuple(response[i] for i in indices))
        node = TreeNode(node_id, depth, tuple(samples[i] for i in indices), mean, error)
        nodes.append(node)
        if (
            depth == parameters.maximum_depth
            or len(indices) < 2 * parameters.minimum_leaf_count
            or error == 0
        ):
            return node_id
        best: tuple[float, str, float, int, tuple[int, ...], tuple[int, ...]] | None = None
        for column in sorted(range(len(columns)), key=lambda j: columns[j]):
            for threshold in thresholds(
                tuple(rows[i][column] for i in indices), parameters.maximum_candidates
            ):
                work += len(indices)
                require(work <= bounds.work_cells, "tree split work bound")
                left = tuple(i for i in indices if rows[i][column] <= threshold)
                right = tuple(i for i in indices if rows[i][column] > threshold)
                if min(len(left), len(right)) < parameters.minimum_leaf_count:
                    continue
                loss = finite(
                    leaf_statistics(tuple(response[i] for i in left))[1]
                    + leaf_statistics(tuple(response[i] for i in right))[1]
                )
                candidate = (loss, columns[column], threshold, column, left, right)
                if best is None or candidate[:3] < best[:3]:
                    best = candidate
        if best is not None and finite(error - best[0]) > parameters.minimum_improvement:
            _, feature, threshold, _, left_rows, right_rows = best
            left_id = build(left_rows, depth + 1)
            right_id = build(right_rows, depth + 1)
            nodes[node_id] = TreeNode(
                node_id,
                depth,
                node.sample_ids,
                mean,
                error,
                feature,
                threshold,
                left_id,
                right_id,
            )
        return node_id

    build(tuple(range(len(rows))), 0)
    return tuple(nodes)


def tree_prediction(
    nodes: tuple[TreeNode, ...], columns: tuple[str, ...], values: tuple[float, ...]
) -> tuple[float, tuple[TreePathStep, ...]]:
    require(bool(nodes) and len(values) == len(columns), "tree prediction shape")
    node = nodes[0]
    path = []
    seen: set[int] = set()
    while node.feature_id is not None:
        require(node.node_id not in seen and len(seen) < 31, "tree prediction cycle/bound")
        seen.add(node.node_id)
        require(
            node.feature_id in columns
            and node.threshold is not None
            and node.left is not None
            and node.right is not None,
            "tree split evidence",
        )
        assert node.threshold is not None and node.left is not None and node.right is not None
        value = values[columns.index(node.feature_id)]
        branch = "left-leq" if value <= node.threshold else "right-gt"
        path.append(TreePathStep(node.node_id, node.feature_id, node.threshold, branch, value))
        child = node.left if branch == "left-leq" else node.right
        require(child < len(nodes), "tree child reference")
        node = nodes[child]
    path.append(TreePathStep(node.node_id, None, None, "leaf", node.value))
    return node.value, tuple(path)
