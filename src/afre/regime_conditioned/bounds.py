"""Per-type stored counts, dimensional limits and canonical payload bounds."""

from dataclasses import fields

from afre.regime_conditioned.artifacts import (
    RegimeConditionedEvaluation,
    RegimeDriftDiagnostic,
    RegimeTransition,
)
from afre.regime_conditioned.regimes import RegimeSnapshot, RegimeTaxonomy
from afre.regime_conditioned.schema import RegimeBounds
from afre.schema import Artifact, require
from afre.serialization import canonical_json


def artifact_limit(value: Artifact, bounds: RegimeBounds) -> int:
    return (
        bounds.taxonomies
        if isinstance(value, RegimeTaxonomy)
        else bounds.snapshots
        if isinstance(value, RegimeSnapshot)
        else bounds.transitions
        if isinstance(value, RegimeTransition)
        else bounds.evaluations
        if isinstance(value, RegimeConditionedEvaluation)
        else bounds.drift_windows
        if isinstance(value, RegimeDriftDiagnostic)
        else bounds.samples
    )


def check_regime_bounds(value: Artifact, bounds: RegimeBounds) -> None:
    require(
        len(canonical_json(value).encode()) <= bounds.serialized_bytes,
        "regime payload byte bound",
    )
    for field in fields(value):
        item = getattr(value, field.name)
        if isinstance(item, Artifact):
            check_regime_bounds(item, bounds)
        elif isinstance(item, tuple):
            limit = (
                bounds.states
                if field.name
                in (
                    "states",
                    "labels",
                    "descriptions",
                    "probabilities",
                    "state_fits",
                    "soft_diagnostics",
                    "state_probability_deltas",
                    "state_error_deltas",
                )
                else bounds.snapshots
                if field.name in ("candidate_ids", "admissible_ids")
                else bounds.transitions
                if field.name == "transition_ids"
                else bounds.audit_nodes
                if field.name == "evidence_ids"
                else bounds.samples
            )
            require(len(item) <= limit, "regime sequence/dimension bound")
            for component in item:
                if isinstance(component, Artifact):
                    check_regime_bounds(component, bounds)
