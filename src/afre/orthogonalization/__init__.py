"""AFRE-16 causal TRAIN-fitted projection and supplied-signal redundancy research."""

from afre.orthogonalization.artifacts import (
    AlignedSignalRow,
    OrthogonalizationAudit,
    OrthogonalSignalValue,
    ProjectionArtifact,
    RedundancyMatrix,
)
from afre.orthogonalization.definitions import OrthogonalizationSpec, SignalReference
from afre.orthogonalization.engine import OrthogonalizationEngine
from afre.orthogonalization.evaluation_artifacts import (
    PartialCorrelation,
    PredictiveModelPair,
    RedundancyEvaluation,
    RedundancyStability,
)
from afre.orthogonalization.repository import OrthogonalizationRepository
from afre.orthogonalization.schema import (
    OrthogonalizationBounds,
    OrthogonalizationMode,
    OrthogonalQuality,
    ProjectionIntercept,
    ProjectionPreprocessing,
    SignalSourceType,
)
from afre.orthogonalization.signals import GenericSignalSource, SignalObservation

__all__ = [
    "AlignedSignalRow",
    "ProjectionArtifact",
    "OrthogonalSignalValue",
    "RedundancyMatrix",
    "OrthogonalizationAudit",
    "OrthogonalizationSpec",
    "SignalReference",
    "GenericSignalSource",
    "SignalObservation",
    "OrthogonalizationMode",
    "ProjectionIntercept",
    "ProjectionPreprocessing",
    "SignalSourceType",
    "OrthogonalQuality",
    "OrthogonalizationBounds",
    "PredictiveModelPair",
    "RedundancyEvaluation",
    "PartialCorrelation",
    "RedundancyStability",
    "OrthogonalizationEngine",
    "OrthogonalizationRepository",
]
