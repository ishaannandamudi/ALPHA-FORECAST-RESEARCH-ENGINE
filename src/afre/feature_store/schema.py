"""Feature-store schema and bounded query policies, independent of AFRE-0 schema."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require

FEATURE_STORE_SCHEMA_VERSION = "1.0"


@enum
class StoreScope(Enum):
    SECURITY = "security"
    ISSUER = "issuer"
    SECTOR = "sector"
    MARKET = "market"
    MACRO = "macro"


@enum
class ValidityRule(Enum):
    LAST_OBSERVATION = "last_observation"
    INTERVAL = "interval"
    KNOWN_FACT = "known_fact"


@enum
class AvailabilityMode(Enum):
    LIVE = "live"
    RECONSTRUCTED = "reconstructed"


@enum
class DeliveryEvidenceKind(Enum):
    AFRE_DELIVERY_LOG = "afre_delivery_log"
    QUALIFIED_CHANNEL_REPLAY = "qualified_channel_replay"


@contract("fs_query_bounds")
@dataclass(frozen=True, slots=True)
class QueryBounds(Artifact):
    origins: int = 1000
    instruments: int = 1000
    features: int = 256
    cells: int = 100_000
    candidates: int = 128
    history: int = 5000
    lineage_depth: int = 64
    lineage_nodes: int = 10_000
    serialized_bytes: int = 8 * 1024 * 1024

    def _validate(self) -> None:
        require(
            all(
                value > 0
                for value in (
                    self.origins,
                    self.instruments,
                    self.features,
                    self.cells,
                    self.candidates,
                    self.history,
                    self.lineage_depth,
                    self.lineage_nodes,
                    self.serialized_bytes,
                )
            ),
            "query bounds must be positive",
        )


@contract("fs_query_policy")
@dataclass(frozen=True, slots=True)
class QueryPolicy(Artifact):
    approved_delivery_attestors: tuple[str, ...] = ()
    compatible_dataset_ids: tuple[str, ...] = ()

    def _normalize(self) -> None:
        for field in ("approved_delivery_attestors", "compatible_dataset_ids"):
            values = getattr(self, field)
            require(len(set(values)) == len(values), "duplicate query policy entry")
            object.__setattr__(self, field, tuple(sorted(values)))

    def _validate(self) -> None:
        from afre.ids import validate_fingerprint

        for identity in self.compatible_dataset_ids:
            validate_fingerprint(identity)
