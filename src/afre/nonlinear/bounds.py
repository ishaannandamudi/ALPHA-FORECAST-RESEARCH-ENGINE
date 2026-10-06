"""Fail before bounded arithmetic, repository scans or serialized artifact publication."""

from afre.nonlinear.artifacts import (
    FittedTransformArtifact,
    InteractionMatrix,
    InteractionStability,
    NonlinearAudit,
    NonlinearEvaluation,
    NonlinearForecast,
    NonlinearInput,
    NonlinearModelArtifact,
)
from afre.nonlinear.definitions import InteractionSet, NonlinearModelSpec
from afre.nonlinear.schema import NonlinearBounds
from afre.schema import Artifact, require
from afre.serialization import canonical_json


def check_nonlinear_bounds(value: Artifact, bounds: NonlinearBounds) -> None:
    require(
        len(canonical_json(value).encode()) <= bounds.serialized_bytes,
        "nonlinear payload byte bound",
    )
    if isinstance(value, InteractionSet):
        require(len(value.definitions) <= bounds.interactions, "runtime interaction bound")
    elif isinstance(value, NonlinearModelSpec):
        check_nonlinear_bounds(value.interaction_set, bounds)
        require(
            len(value.features) <= bounds.features and len(value.columns) <= bounds.features,
            "runtime model feature bound",
        )
        if value.tree:
            require(
                value.tree.maximum_depth <= bounds.tree_depth
                and value.tree.maximum_candidates <= bounds.split_candidates,
                "runtime tree specification bound",
            )
    elif isinstance(value, NonlinearInput):
        require(len(value.scalars) <= bounds.features, "runtime input feature bound")
    elif isinstance(value, FittedTransformArtifact):
        require(
            len(value.train_input_ids) <= bounds.training_rows, "runtime transform row bound"
        )
    elif isinstance(value, InteractionMatrix):
        require(
            len(value.rows) <= bounds.training_rows
            and len(value.columns) <= bounds.features
            and len(value.rows) * len(value.columns) <= bounds.work_cells,
            "runtime matrix work bound",
        )
    elif isinstance(value, NonlinearModelArtifact):
        require(
            len(value.train_sample_ids) <= bounds.training_rows
            and len(value.columns) <= bounds.features
            and len(value.nodes) <= 2 ** (bounds.tree_depth + 1) - 1
            and all(n.depth <= bounds.tree_depth for n in value.nodes),
            "runtime model/tree bound",
        )
    elif isinstance(value, NonlinearEvaluation):
        require(len(value.forecast_ids) <= bounds.forecasts, "runtime evaluation bound")
    elif isinstance(value, NonlinearForecast):
        require(
            len(value.interaction_ids) <= bounds.interactions
            and len(value.column_values) <= bounds.features,
            "runtime forecast bound",
        )
    elif isinstance(value, InteractionStability):
        require(len(value.model_ids) <= bounds.evaluations, "runtime stability bound")
    elif isinstance(value, NonlinearAudit):
        require(len(value.node_ids) <= bounds.audit_nodes, "runtime lineage node bound")


def artifact_limit(value: Artifact, bounds: NonlinearBounds) -> int:
    return (
        bounds.evaluations
        if isinstance(value, (NonlinearEvaluation, InteractionStability, NonlinearAudit))
        else bounds.artifacts
    )
