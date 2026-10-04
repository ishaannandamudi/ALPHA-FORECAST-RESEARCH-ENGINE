"""Closed target policies and independent target schema/bounds."""

from dataclasses import dataclass
from enum import Enum

from afre.schema import Artifact, contract, enum, require
from afre.version import TARGET_SCHEMA_VERSION as TARGET_SCHEMA_VERSION

BUILDER_VERSION = "afre-target-builder-v1"


@enum
class TargetOriginPolicy(Enum):
    EXACT = "exact_origin"
    LAST_AT_OR_BEFORE = "last_completed_at_or_before_origin"
    FIRST_AFTER = "first_completed_strictly_after_origin"


@enum
class TargetEndpointPolicy(Enum):
    EXACT = "exact_endpoint"
    LAST_AT_OR_BEFORE = "last_completed_at_or_before_endpoint"
    FIRST_AT_OR_AFTER = "first_completed_at_or_after_endpoint"


@enum
class TargetPriceField(Enum):
    CLOSE = "close"


@enum
class TargetSessionPolicy(Enum):
    REGULAR_ONLY = "regular_only"
    INCLUDE_EXTENDED = "include_extended"


@enum
class TargetPathRule(Enum):
    FAIL_MISSING = "fail_missing"
    MINIMUM_COVERAGE = "minimum_coverage"


@enum
class TargetObservationState(Enum):
    VALID = "valid"
    MISSING = "missing_print"
    HALTED = "halted"
    DELISTED = "delisted"
    NONPOSITIVE_PRICE = "nonpositive_price"


@enum
class TargetAggregation(Enum):
    SIMPLE = "endpoint_simple_return"
    LOG = "endpoint_log_return"
    ABSOLUTE = "absolute_simple_return"
    RESIDUAL = "supplied_benchmark_subtraction"
    DOWNSIDE = "minimum_simple_return_zero"
    VOLATILITY = "sqrt_sum_squared_close_log_returns"
    ADVERSE = "minimum_signed_close_excursion_with_zero"
    FAVORABLE = "maximum_signed_close_excursion_with_zero"


@enum
class TargetQualityFlag(Enum):
    TOLERATED_ORIGIN = "tolerated_origin"
    TOLERATED_ENDPOINT = "tolerated_endpoint"
    PARTIAL_PATH = "partial_path"
    MISSING_PRINT = "missing_print"
    HALTED = "halted"
    DELISTED = "delisted"
    NONPOSITIVE_PRICE = "nonpositive_price"
    SOURCE_REVISION = "source_revision"
    RECONSTRUCTED_SOURCE = "reconstructed_source"
    UNVERIFIED_SOURCE = "unverified_source"


@contract("target_bounds")
@dataclass(frozen=True, slots=True)
class TargetBounds(Artifact):
    origins: int = 1000
    instruments: int = 1000
    targets: int = 64
    rows: int = 100_000
    path_observations: int = 5000
    source_observations: int = 100_000
    lineage_depth: int = 64
    lineage_nodes: int = 100_000
    serialized_bytes: int = 8 * 1024 * 1024

    def _validate(self) -> None:
        require(
            all(
                value > 0
                for value in (
                    self.origins,
                    self.instruments,
                    self.targets,
                    self.rows,
                    self.path_observations,
                    self.source_observations,
                    self.lineage_depth,
                    self.lineage_nodes,
                    self.serialized_bytes,
                )
            ),
            "target bounds must be positive",
        )
