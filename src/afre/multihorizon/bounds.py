"""Allocation, publication and read limits for every multi-horizon result."""

from afre.multihorizon.artifacts import (
    CovarianceArtifact,
    MultiHorizonEvaluation,
    MultiHorizonFitRun,
    MultiHorizonForecast,
    MultiHorizonLineageAudit,
    SharedParameters,
)
from afre.multihorizon.definitions import MultiHorizonModelSpec
from afre.multihorizon.horizon_sets import HorizonSet
from afre.multihorizon.schema import MultiHorizonBounds
from afre.schema import Artifact, require
from afre.serialization import canonical_json


def check_bounds(value: Artifact, b: MultiHorizonBounds) -> None:
    if isinstance(value, HorizonSet):
        require(len(value.targets) <= b.horizons, "horizon bound")
    elif isinstance(value, MultiHorizonModelSpec):
        check_bounds(value.horizon_set, b)
        require(len(value.sharing) <= b.horizons * 5, "sharing bound")
    elif isinstance(value, MultiHorizonFitRun):
        require(
            len(value.train) <= b.horizons
            and sum(len(t.sample_ids) for t in value.train) <= b.samples
            and len(value.intersection) <= b.samples,
            "fit evidence bound",
        )
    elif isinstance(value, (SharedParameters, CovarianceArtifact)):
        rows = value.sample_rows if isinstance(value, SharedParameters) else value.rows
        require(
            len(rows) <= b.samples and len(rows) * len(rows[0].responses) ** 2 <= b.work_cells,
            "shared/dependence evidence bound",
        )
        if isinstance(value, SharedParameters):
            require(len(value.feature_ids) <= b.features, "shared feature bound")
        else:
            require(len(value.horizon_ids) <= b.horizons, "covariance dimension bound")
    elif isinstance(value, MultiHorizonForecast):
        require(len(value.entries) <= b.horizons, "bundle horizon bound")
    elif isinstance(value, MultiHorizonEvaluation):
        require(
            len(value.bundle_ids) <= b.forecasts
            and len(value.horizons) <= b.horizons
            and len(value.matched_origins) <= b.samples,
            "evaluation bound",
        )
    elif isinstance(value, MultiHorizonLineageAudit):
        require(len(value.evidence_ids) <= b.audit_nodes, "lineage node bound")
    require(
        len(canonical_json(value).encode()) <= b.serialized_bytes, "multi-horizon byte bound"
    )
