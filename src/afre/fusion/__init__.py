"""AFRE21 immutable fixed and TRAIN-fitted ensemble and signal fusion."""

from afre.fusion.accounting import FusionTrialPool
from afre.fusion.artifacts import (
    FrozenFusionTestChoice,
    FusedForecast,
    FusionArtifact,
    FusionContribution,
    FusionObservation,
    FusionTrainingRow,
)
from afre.fusion.definitions import FusionSourceReference, FusionSpec
from afre.fusion.diagnostics import DiversityMatrix, FusionComparison, FusionWeightStability
from afre.fusion.engine import FusionEngine
from afre.fusion.external import ExternalFusionDefinition, ExternalFusionOutput
from afre.fusion.lineage import FusionAudit
from afre.fusion.probabilistic import FusionDistribution
from afre.fusion.repository import FusionRepository
from afre.fusion.schema import (
    FusionBounds,
    FusionFamily,
    FusionIntercept,
    FusionKind,
    FusionMissingness,
    FusionNormalization,
    FusionStatus,
    FusionWeights,
)

__all__ = [
    "FusionTrialPool",
    "FusedForecast",
    "FusionArtifact",
    "FusionContribution",
    "FusionObservation",
    "FusionTrainingRow",
    "FrozenFusionTestChoice",
    "FusionSourceReference",
    "FusionSpec",
    "DiversityMatrix",
    "FusionComparison",
    "FusionWeightStability",
    "FusionEngine",
    "ExternalFusionDefinition",
    "ExternalFusionOutput",
    "FusionAudit",
    "FusionDistribution",
    "FusionRepository",
    "FusionBounds",
    "FusionFamily",
    "FusionIntercept",
    "FusionKind",
    "FusionMissingness",
    "FusionNormalization",
    "FusionStatus",
    "FusionWeights",
]
