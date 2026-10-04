"""AFRE-2 target truth layer; no feature conversion or model fitting."""

from afre.target_engine.corporate_actions import (
    TargetActionKind,
    TargetActionStream,
    TargetCorporateAction,
)
from afre.target_engine.definitions import (
    TargetDefinition,
    TargetEndpointRules,
    TargetPathPolicy,
    TargetSetManifest,
)
from afre.target_engine.engine import TargetEngine
from afre.target_engine.market_data import (
    TargetBar,
    TargetMarketDataProvider,
    TargetMarketSource,
    TargetSourceBuild,
)
from afre.target_engine.models import TargetAudit, TargetDatasetManifest, TargetVintage
from afre.target_engine.quality import TargetQuality
from afre.target_engine.repository import TargetRepository
from afre.target_engine.residuals import BenchmarkReference, SuppliedBenchmarkReturn
from afre.target_engine.schema import TARGET_SCHEMA_VERSION, TargetBounds
from afre.target_engine.validation import target_known_by_cutoff
from afre.target_engine.windows import TargetCalendar, TargetSession

__all__ = [
    "TargetDefinition",
    "TargetEndpointRules",
    "TargetPathPolicy",
    "TargetSetManifest",
    "TargetEngine",
    "TargetRepository",
    "TargetBar",
    "TargetMarketSource",
    "TargetSourceBuild",
    "TargetMarketDataProvider",
    "TargetVintage",
    "TargetDatasetManifest",
    "TargetAudit",
    "TargetQuality",
    "TargetActionKind",
    "TargetActionStream",
    "TargetCorporateAction",
    "BenchmarkReference",
    "SuppliedBenchmarkReturn",
    "TargetBounds",
    "TARGET_SCHEMA_VERSION",
    "TargetCalendar",
    "TargetSession",
    "target_known_by_cutoff",
]
