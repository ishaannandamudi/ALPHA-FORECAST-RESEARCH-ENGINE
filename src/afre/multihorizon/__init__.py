"""AFRE-8: exact causal multi-horizon composition; no automated model selection."""

from afre.multihorizon.artifacts import (
    AlignedTrainRow,
    ConsistencyAudit,
    CovarianceArtifact,
    HorizonEvaluation,
    HorizonForecastEntry,
    HorizonTrainEvidence,
    MultiHorizonEvaluation,
    MultiHorizonFitRun,
    MultiHorizonForecast,
    MultiHorizonLineageAudit,
    SharedParameters,
    SharedPointForecast,
    SurfaceRow,
    SurfaceValue,
)
from afre.multihorizon.definitions import (
    HorizonModelBinding,
    MultiHorizonModelSpec,
    ParameterSharing,
    sharing_for,
)
from afre.multihorizon.engine import MultiHorizonEngine
from afre.multihorizon.forecasts import forecast_for_horizon, surfaces
from afre.multihorizon.horizon_sets import HorizonSet
from afre.multihorizon.repository import MultiHorizonRepository
from afre.multihorizon.schema import (
    Architecture,
    Completeness,
    ComponentState,
    Denominator,
    DependenceMethod,
    HorizonOrder,
    MultiHorizonBounds,
    ParameterOwnership,
)

__all__ = [
    "AlignedTrainRow",
    "ConsistencyAudit",
    "CovarianceArtifact",
    "HorizonEvaluation",
    "HorizonForecastEntry",
    "HorizonTrainEvidence",
    "MultiHorizonEvaluation",
    "MultiHorizonFitRun",
    "MultiHorizonForecast",
    "MultiHorizonLineageAudit",
    "SharedParameters",
    "SharedPointForecast",
    "SurfaceRow",
    "SurfaceValue",
    "HorizonModelBinding",
    "MultiHorizonModelSpec",
    "ParameterSharing",
    "sharing_for",
    "MultiHorizonEngine",
    "forecast_for_horizon",
    "surfaces",
    "HorizonSet",
    "MultiHorizonRepository",
    "Architecture",
    "Completeness",
    "ComponentState",
    "Denominator",
    "DependenceMethod",
    "HorizonOrder",
    "MultiHorizonBounds",
    "ParameterOwnership",
]
