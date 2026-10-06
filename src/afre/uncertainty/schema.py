"""Closed uncertainty semantics; diagnostic categories never imply causal attribution."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require

UNCERTAINTY_IMPLEMENTATION = "identified-uncertainty-v1"


@enum
class UncertaintyType(Enum):
    TOTAL_PREDICTIVE = "total_predictive"
    ALEATORIC = "aleatoric"
    PARAMETER = "parameter"
    MODEL_SPECIFICATION = "model_specification"
    EXPERT_DISAGREEMENT = "expert_disagreement"
    WITHIN_EXPERT_PREDICTIVE = "within_expert_predictive"
    REGIME_AMBIGUITY = "regime_ambiguity"
    EVENT_AMBIGUITY = "event_ambiguity"
    DATA_QUALITY = "data_quality"
    HORIZON = "horizon"
    RESIDUAL_UNATTRIBUTED = "residual_unattributed"


@enum
class IdentifiabilityStatus(Enum):
    IDENTIFIED = "identified"
    PARTIALLY_IDENTIFIED = "partially_identified"
    PROXY_ONLY = "proxy_only"
    UNIDENTIFIABLE = "unidentifiable"
    INSUFFICIENT_DATA = "insufficient_data"
    UNAVAILABLE = "unavailable"
    INCOMPATIBLE = "incompatible"


@enum
class UncertaintyMeasure(Enum):
    VARIANCE = "variance"
    STANDARD_DEVIATION = "standard_deviation"
    INTERVAL_WIDTH = "interval_width"
    ENTROPY = "entropy"
    DISAGREEMENT = "disagreement"
    SCORE_VARIANCE = "score_variance"
    QUALITY_PENALTY = "quality_penalty"


@enum
class ClosurePolicy(Enum):
    EXACT_ADDITIVE = "exact_additive"
    APPROXIMATE_ADDITIVE = "approximate_additive"
    NON_ADDITIVE_DIAGNOSTICS_ONLY = "non_additive_diagnostics_only"


@enum
class CovarianceAssumption(Enum):
    IID_HOMOSKEDASTIC_CORRECT_LINEAR = "iid-homoskedastic-correct-fixed-linear-design"


@contract("unc_bounds")
@dataclass(frozen=True, slots=True)
class UncertaintyBounds(Artifact):
    components: int = 16
    samples: int = 2000
    dimensions: int = 17
    experts: int = 32
    buckets: int = 20
    drift_windows: int = 32
    cohorts: int = 128
    artifacts: int = 20_000
    work_cells: int = 2_000_000
    serialized_bytes: int = 8_388_608
    audit_nodes: int = 100_000
    audit_depth: int = 64

    def _validate(self) -> None:
        values = (
            self.components,
            self.samples,
            self.dimensions,
            self.experts,
            self.buckets,
            self.drift_windows,
            self.cohorts,
            self.artifacts,
            self.work_cells,
            self.serialized_bytes,
            self.audit_nodes,
            self.audit_depth,
        )
        limits = (16, 2000, 17, 32, 20, 32, 128, 20_000, 2_000_000, 8_388_608, 100_000, 64)
        require(
            all(1 <= v <= m for v, m in zip(values, limits, strict=True)),
            "uncertainty hard resource bound",
        )
