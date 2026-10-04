"""Explicit immutable outcome definitions without changing foundation TargetSpec."""

import re
from dataclasses import dataclass

from afre.datasets import AdjustmentPolicy
from afre.horizons import ForecastHorizon
from afre.ids import validate_fingerprint
from afre.lineage import Parameter
from afre.schema import Artifact, contract, require
from afre.target_engine.residuals import BenchmarkReference
from afre.target_engine.schema import (
    BUILDER_VERSION,
    TargetAggregation,
    TargetEndpointPolicy,
    TargetOriginPolicy,
    TargetPathRule,
    TargetPriceField,
    TargetSessionPolicy,
)
from afre.targets import TargetType


@contract("target_endpoints")
@dataclass(frozen=True, slots=True)
class TargetEndpointRules(Artifact):
    origin: TargetOriginPolicy = TargetOriginPolicy.EXACT
    endpoint: TargetEndpointPolicy = TargetEndpointPolicy.EXACT
    origin_tolerance_ns: int = 0
    endpoint_tolerance_ns: int = 0

    def _validate(self) -> None:
        require(
            self.origin is not TargetOriginPolicy.EXACT or self.origin_tolerance_ns == 0,
            "exact origin cannot have tolerance",
        )
        require(
            self.endpoint is not TargetEndpointPolicy.EXACT or self.endpoint_tolerance_ns == 0,
            "exact endpoint cannot have tolerance",
        )
        require(
            self.origin is not TargetOriginPolicy.FIRST_AFTER or self.origin_tolerance_ns > 0,
            "first-after origin requires explicit positive tolerance",
        )


@contract("target_path_policy")
@dataclass(frozen=True, slots=True)
class TargetPathPolicy(Artifact):
    interval_ns: int
    minimum_observations: int = 1
    rule: TargetPathRule = TargetPathRule.FAIL_MISSING
    minimum_coverage: float = 1.0
    annualization_factor: float | None = None

    def _validate(self) -> None:
        require(
            self.interval_ns > 0 and self.minimum_observations > 0,
            "positive sampling interval/minimum required",
        )
        require(0 < self.minimum_coverage <= 1, "invalid minimum path coverage")
        require(
            self.rule is not TargetPathRule.FAIL_MISSING or self.minimum_coverage == 1,
            "fail-missing path must require full coverage",
        )
        require(
            self.annualization_factor is None or self.annualization_factor > 0,
            "positive annualization factor required",
        )


@contract("target_definition")
@dataclass(frozen=True, slots=True)
class TargetDefinition(Artifact):
    name: str
    version: str
    target_type: TargetType
    horizon: ForecastHorizon
    endpoints: TargetEndpointRules
    adjustment: AdjustmentPolicy
    aggregation: TargetAggregation
    source_dataset_ids: tuple[str, ...]
    calendar_id: str
    bar_definition: str
    benchmark: BenchmarkReference | None = None
    path: TargetPathPolicy | None = None
    price_field: TargetPriceField = TargetPriceField.CLOSE
    session_policy: TargetSessionPolicy = TargetSessionPolicy.REGULAR_ONLY
    implementation_version: str = BUILDER_VERSION
    parameters: tuple[Parameter, ...] = ()

    def _normalize(self) -> None:
        self.ordered("parameters", "name")
        require(
            len(set(self.source_dataset_ids)) == len(self.source_dataset_ids),
            "duplicate target datasets",
        )
        object.__setattr__(self, "source_dataset_ids", tuple(sorted(self.source_dataset_ids)))

    def _validate(self) -> None:
        require(
            re.fullmatch(r"target\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*", self.name)
            is not None,
            "target namespace required",
        )
        require(bool(self.source_dataset_ids), "target source dataset required")
        for identity in self.source_dataset_ids:
            validate_fingerprint(identity)
        expected = {
            TargetType.SIMPLE_RETURN: TargetAggregation.SIMPLE,
            TargetType.LOG_RETURN: TargetAggregation.LOG,
            TargetType.RESIDUAL_RETURN: TargetAggregation.RESIDUAL,
            TargetType.ABSOLUTE_RETURN: TargetAggregation.ABSOLUTE,
            TargetType.REALIZED_VOLATILITY: TargetAggregation.VOLATILITY,
            TargetType.DOWNSIDE_RETURN: TargetAggregation.DOWNSIDE,
            TargetType.MAX_ADVERSE_EXCURSION: TargetAggregation.ADVERSE,
            TargetType.MAX_FAVORABLE_EXCURSION: TargetAggregation.FAVORABLE,
        }
        require(
            self.aggregation is expected[self.target_type], "target estimator/type mismatch"
        )
        require(
            (self.benchmark is not None) == (self.target_type is TargetType.RESIDUAL_RETURN),
            "residual target requires exact benchmark",
        )
        if self.benchmark is not None:
            require(
                self.benchmark.dataset_id in self.source_dataset_ids,
                "benchmark dataset undeclared",
            )
        if self.adjustment.source_dataset_id is not None:
            require(
                self.adjustment.source_dataset_id in self.source_dataset_ids,
                "action dataset undeclared",
            )
        needs_path = self.target_type in (
            TargetType.REALIZED_VOLATILITY,
            TargetType.MAX_ADVERSE_EXCURSION,
            TargetType.MAX_FAVORABLE_EXCURSION,
        )
        require(needs_path == (self.path is not None), "target path estimator/policy mismatch")
        if self.path is not None:
            require(
                self.endpoints == TargetEndpointRules(),
                "path estimators require exact origin and endpoint",
            )
            require(
                self.target_type is TargetType.REALIZED_VOLATILITY
                or self.path.annualization_factor is None,
                "annualization only applies to volatility",
            )
        require(
            self.horizon.calendar_id is None or self.horizon.calendar_id == self.calendar_id,
            "target horizon/calendar mismatch",
        )
        require(
            self.horizon.bar_definition is None
            or self.horizon.bar_definition == self.bar_definition,
            "target horizon/bar stream mismatch",
        )
        require(
            not self.parameters, "initial target estimators accept no unspecified parameters"
        )


@contract("target_set")
@dataclass(frozen=True, slots=True)
class TargetSetManifest(Artifact):
    definitions: tuple[TargetDefinition, ...]

    def _normalize(self) -> None:
        self.ordered("definitions", "fingerprint")

    def _validate(self) -> None:
        require(bool(self.definitions), "empty target set")
        keys = [(item.name, item.version) for item in self.definitions]
        require(len(keys) == len(set(keys)), "conflicting target revisions")
