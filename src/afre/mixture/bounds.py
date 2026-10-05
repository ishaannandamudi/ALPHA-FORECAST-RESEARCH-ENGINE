"""Configured per-artifact dimensions, stored counts and canonical payload limits."""

from dataclasses import fields

from afre.mixture.artifacts import MixtureEvaluation
from afre.mixture.schema import MixtureBounds
from afre.schema import Artifact, require
from afre.serialization import canonical_json


def artifact_limit(value: Artifact, bounds: MixtureBounds) -> int:
    return bounds.evaluations if isinstance(value, MixtureEvaluation) else bounds.forecasts


def check_mixture_bounds(value: Artifact, bounds: MixtureBounds) -> None:
    require(
        len(canonical_json(value).encode()) <= bounds.serialized_bytes,
        "mixture payload byte bound",
    )
    for field in fields(value):
        item = getattr(value, field.name)
        if isinstance(item, Artifact):
            check_mixture_bounds(item, bounds)
        elif isinstance(item, tuple):
            limit = (
                bounds.experts
                if field.name
                in ("experts", "expert_inputs", "weights", "contributions", "comparisons")
                else bounds.components
                if field.name == "components"
                else bounds.atoms
                if field.name == "samples"
                else bounds.gating_features
                if field.name in ("feature_ids", "gating_feature_ids")
                else bounds.experts**2
                if field.name == "correlations"
                else bounds.training_samples
                if field.name == "rows"
                else bounds.audit_nodes
                if field.name == "evidence_ids"
                else bounds.forecasts
            )
            require(len(item) <= limit, "mixture dimension/sequence bound")
            for part in item:
                if isinstance(part, Artifact):
                    check_mixture_bounds(part, bounds)
