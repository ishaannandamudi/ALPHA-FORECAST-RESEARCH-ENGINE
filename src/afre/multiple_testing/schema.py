"""Closed evidence semantics; none of these operations selects or promotes models."""

from dataclasses import dataclass, fields
from enum import Enum

from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, enum, require

MULTIPLE_TESTING_SCHEMA_VERSION = "1.0"
IMPLEMENTATION = "declared-family-exact-sign-controls-v1"


@enum
class HypothesisDirection(Enum):
    TWO_SIDED = "two_sided"
    GREATER = "greater"
    LESS = "less"


@enum
class CorrectionMethod(Enum):
    BONFERRONI = "bonferroni"
    HOLM = "holm"
    BENJAMINI_HOCHBERG = "benjamini_hochberg"
    BENJAMINI_YEKUTIELI = "benjamini_yekutieli"


@enum
class DependenceAssumption(Enum):
    INDEPENDENT = "independent"
    PRDS = "positive_regression_dependence_on_true_nulls"
    ARBITRARY = "arbitrary"
    UNKNOWN = "unknown"


@enum
class RawTestMethod(Enum):
    EXACT_SIGN = "exact_conditional_sign"
    EXACT_PAIRED_SIGN = "exact_paired_conditional_sign"
    NORMAL_MEAN = "unsupported_normal_mean"
    CORRELATION = "unsupported_correlation"


@enum
class ResearchMetric(Enum):
    TARGET_RETURN = "target_return"
    FORECAST_ERROR = "forecast_minus_truth"
    ABSOLUTE_ERROR = "absolute_forecast_error"
    SQUARED_ERROR = "squared_forecast_error"
    NET_CONTRIBUTION = "hypothetical_cost_net_contribution"
    RESIDUAL_VALUE = "orthogonal_residual_value"


@enum
class TrialState(Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


@enum
class EvidenceState(Enum):
    AVAILABLE = "available"
    UNSUPPORTED = "unsupported"
    INSUFFICIENT = "insufficient"
    INCOMPATIBLE = "incompatible"
    INTERIM = "interim"


@enum
class FamilyCompleteness(Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    OPEN = "open"
    INVALID = "invalid"


@enum
class AdaptiveTrialStatus(Enum):
    PREDECLARED = "caller_attested_predeclared"
    ADAPTIVE = "adaptive"
    UNKNOWN = "unknown"


@enum
class TestReuseStatus(Enum):
    FIRST_USE = "first_registered_use"
    REUSED = "reused"
    HEAVILY_REUSED = "heavily_reused"
    UNTRACKED = "untracked_native_history"
    INCOMPATIBLE = "incompatible"


@enum
class DescriptiveSelectionRule(Enum):
    MAX_METRIC = "max_metric"
    MIN_ERROR = "min_error"
    TOP_K = "top_k"
    DECLARED_THRESHOLD = "declared_threshold"


@contract("mt_bounds")
@dataclass(frozen=True, slots=True)
class MultipleTestingBounds(Artifact):
    trials: int = 2000
    hypotheses: int = 2000
    samples: int = 2000
    metrics: int = 16
    test_history: int = 2000
    selection_events: int = 256
    registry_snapshots: int = 256
    artifacts: int = 20000
    serialized_bytes: int = 8388608
    audit_nodes: int = 100000
    audit_depth: int = 64

    def _validate(self) -> None:
        maxima = (2000, 2000, 2000, 16, 2000, 256, 256, 20000, 8388608, 100000, 64)
        require(
            all(
                1 <= getattr(self, f.name) <= m
                for f, m in zip(fields(self), maxima, strict=True)
            ),
            "multiple testing bounds",
        )


def ids(value: Artifact, *names: str) -> None:
    for name in names:
        items = getattr(value, name)
        require(len(set(items)) == len(items), "duplicate research reference")
        for identity in items:
            validate_fingerprint(identity)
        object.__setattr__(value, name, tuple(sorted(items)))


def metric_unit(metric: ResearchMetric) -> str:
    return (
        "squared_return_fraction"
        if metric is ResearchMetric.SQUARED_ERROR
        else "return_fraction"
        if metric is not ResearchMetric.RESIDUAL_VALUE
        else "native_residual_unit"
    )
