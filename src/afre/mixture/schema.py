"""Closed data-only composition policies and explicit resource ceilings."""

from dataclasses import dataclass, fields
from enum import Enum

from afre.schema import Artifact, contract, enum, require

MIXTURE_IMPLEMENTATION = "mixture-v1"


@enum
class ExpertKind(Enum):
    AFRE_POINT = "afre_point"
    AFRE_PROBABILISTIC = "afre_probabilistic"
    AFRE_EVENT = "afre_event"
    AFRE_REGIME = "afre_regime"
    EXTERNAL_MICROSTRUCTURE = "external_microstructure"
    EXTERNAL_CONTEXT = "external_context"
    EXTERNAL_OPTIONS = "external_options"
    EXTERNAL_GENERIC = "external_generic"


@enum
class ExpertOutput(Enum):
    POINT = "point"
    PROBABILISTIC = "probabilistic"
    CALIBRATED_PROBABILISTIC = "calibrated_probabilistic"


@enum
class ExpertQuality(Enum):
    VALID = "valid"
    MISSING = "missing"
    STALE = "stale"
    DEGRADED = "degraded"
    UNSUPPORTED = "unsupported"
    INVALID = "invalid"


@enum
class GateMode(Enum):
    FIXED = "fixed"
    LEARNED_LINEAR = "learned_linear"


@enum
class ExpertMissingPolicy(Enum):
    FAIL = "fail"
    DROP_AND_RENORMALIZE = "drop_and_renormalize"
    USE_DECLARED_FALLBACK = "use_declared_fallback"


@enum
class MixtureCalibrationStatus(Enum):
    SUPPORTED = "supported"
    INSUFFICIENT_DATA = "insufficient_data"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"


@contract("mix_bounds")
@dataclass(frozen=True, slots=True)
class MixtureBounds(Artifact):
    experts: int = 32
    gating_features: int = 64
    training_samples: int = 50_000
    forecasts: int = 100_000
    components: int = 32
    atoms: int = 10_000
    evaluations: int = 1000
    work_cells: int = 2_000_000
    audit_nodes: int = 100_000
    audit_depth: int = 64
    serialized_bytes: int = 8 * 1024 * 1024

    def _validate(self) -> None:
        require(all(getattr(self, f.name) > 0 for f in fields(self)), "positive mixture bounds")
        require(
            self.experts <= 256
            and self.components <= 256
            and self.gating_features <= 1024
            and self.audit_depth <= 64
            and self.serialized_bytes <= 16 * 1024 * 1024
            and max(self.training_samples, self.forecasts, self.atoms, self.audit_nodes)
            <= 1_000_000,
            "mixture hard bounds",
        )
