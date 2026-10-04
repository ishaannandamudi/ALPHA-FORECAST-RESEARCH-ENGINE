"""AFRE-0 foundation; static imports establish the safe contract allowlist."""

from afre.datasets import DatasetManifest, ForecastFeatureRow, UniverseManifest
from afre.experiments import ExperimentResult, ExperimentSpec
from afre.features import FeatureDefinition, FeatureSet, FeatureValue
from afre.forecast import ForecastOrigin
from afre.horizons import ForecastHorizon
from afre.ids import InstrumentId
from afre.models import ModelArtifact, ModelSpec
from afre.providers import EventSnapshotRef
from afre.targets import ForecastTargetRow, TargetSpec
from afre.version import ENGINE_VERSION, FOUNDATION_SCHEMA_VERSION, STORE_SCHEMA_VERSION

__all__ = [
    "DatasetManifest",
    "ForecastFeatureRow",
    "UniverseManifest",
    "ExperimentResult",
    "ExperimentSpec",
    "FeatureDefinition",
    "FeatureSet",
    "FeatureValue",
    "ForecastOrigin",
    "ForecastHorizon",
    "InstrumentId",
    "ModelArtifact",
    "ModelSpec",
    "EventSnapshotRef",
    "ForecastTargetRow",
    "TargetSpec",
    "ENGINE_VERSION",
    "FOUNDATION_SCHEMA_VERSION",
    "STORE_SCHEMA_VERSION",
]
