"""Immutable source identity, predeclared source sets and finite policies."""

from dataclasses import dataclass
from math import fsum

from afre.fusion.schema import (
    IMPLEMENTATION,
    FusionBounds,
    FusionFamily,
    FusionIntercept,
    FusionKind,
    FusionMissingness,
    FusionNormalization,
    FusionWeights,
)
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require


@contract("fus_source")
@dataclass(frozen=True, slots=True)
class FusionSourceReference(Artifact):
    source_id: str
    family: str
    artifact_id: str
    version: str
    provider: str
    target_id: str
    horizon_id: str
    kind: FusionKind
    unit: str
    model_id: str
    spec_id: str
    calibration_state: str
    available_ns: int
    anchor_output_id: str

    def _validate(self) -> None:
        for i in (
            self.artifact_id,
            self.target_id,
            self.horizon_id,
            self.model_id,
            self.spec_id,
            self.anchor_output_id,
        ):
            validate_fingerprint(i)
        require(
            self.family
            in (
                "point",
                "probabilistic",
                "calibrated",
                "event",
                "regime",
                "mixture",
                "nonlinear",
                "sequence",
                "orthogonal",
                "external",
            ),
            "closed fusion source family",
        )


@contract("fus_spec")
@dataclass(frozen=True, slots=True)
class FusionSpec(Artifact):
    name: str
    source_ids: tuple[str, ...]
    target_id: str
    horizon_id: str
    kind: FusionKind
    unit: str
    family: FusionFamily
    weight_policy: FusionWeights
    weights: tuple[tuple[str, float], ...]
    dataset_id: str
    fold_id: str
    declared_ns: int
    missingness: FusionMissingness = FusionMissingness.FAIL
    normalization: FusionNormalization = FusionNormalization.NONE
    intercept_policy: FusionIntercept = FusionIntercept.NO_INTERCEPT
    fixed_intercept: float = 0.0
    fallback_source_id: str | None = None
    allow_distinct_versions: bool = False
    rank_tolerance: float = 1e-12
    condition_limit: float = 1e10
    tolerance: float = 1e-12
    seed: int = 0
    bounds: FusionBounds = FusionBounds()
    validation_context: str = "frozen-single-artifact-no-selection"
    source_selection_result_id: str | None = None
    output_unit: str | None = None
    implementation: str = IMPLEMENTATION

    def _normalize(self) -> None:
        object.__setattr__(self, "source_ids", tuple(sorted(self.source_ids)))
        object.__setattr__(self, "weights", tuple(sorted(self.weights)))

    def _validate(self) -> None:
        require(
            0 < len(self.source_ids) <= self.bounds.sources
            and len(set(self.source_ids)) == len(self.source_ids),
            "fusion source grid",
        )
        for i in (
            *self.source_ids,
            self.target_id,
            self.horizon_id,
            self.dataset_id,
            self.fold_id,
        ):
            validate_fingerprint(i)
        require(
            self.implementation == IMPLEMENTATION
            and 0 <= self.seed <= 2**32 - 1
            and 0 < self.rank_tolerance < 1
            and self.condition_limit >= 1
            and 0 < self.tolerance <= 1e-12,
            "fusion implementation/numerical policy",
        )
        learned = self.family is FusionFamily.LEARNED_LINEAR_POINT
        require(
            (self.weight_policy is FusionWeights.UNCONSTRAINED_QR) == learned,
            "explicit unconstrained TRAIN linear weights",
        )
        if learned:
            require(
                not self.weights
                and self.fixed_intercept == 0.0
                and self.normalization is FusionNormalization.NONE,
                "learned linear policies",
            )
        else:
            require(
                tuple(i for i, _ in self.weights) == self.source_ids,
                "exact fixed weight source grid",
            )
            require(
                self.intercept_policy is FusionIntercept.WITH_INTERCEPT
                or self.fixed_intercept == 0.0,
                "explicit intercept policy",
            )
        expected = (
            FusionKind.PROBABILISTIC
            if self.family is FusionFamily.FIXED_PROBABILITY_MIXTURE
            else FusionKind.SCALAR_SIGNAL
            if self.family is FusionFamily.FIXED_SIGNAL_BLEND
            else FusionKind.POINT
        )
        require(self.kind is expected, "fusion family/output compatibility")
        if self.kind is FusionKind.PROBABILISTIC:
            require(
                self.weight_policy is FusionWeights.SIMPLEX and self.fixed_intercept == 0.0,
                "probability mixture requires simplex/no intercept",
            )
        if self.weight_policy is FusionWeights.SIMPLEX:
            require(
                all(w >= 0 for _, w in self.weights) and fsum(w for _, w in self.weights) > 0,
                "nonnegative positive-total simplex weights",
            )
            if self.normalization is not FusionNormalization.EXPLICIT_SIMPLEX:
                require(
                    abs(fsum(w for _, w in self.weights) - 1.0) <= self.tolerance,
                    "simplex weight sum",
                )
        require(
            self.normalization is not FusionNormalization.EXPLICIT_SIMPLEX
            or self.weight_policy is FusionWeights.SIMPLEX,
            "explicit simplex normalization",
        )
        require(
            self.normalization is not FusionNormalization.TRAIN_STANDARDIZE
            or self.kind is FusionKind.SCALAR_SIGNAL,
            "TRAIN standardization signal only",
        )
        require(
            self.output_unit == "dimensionless"
            if self.normalization is FusionNormalization.TRAIN_STANDARDIZE
            else self.output_unit in (None, self.unit),
            "explicit standardized output units",
        )
        require(
            self.normalization is not FusionNormalization.TRAIN_STANDARDIZE
            or self.missingness is not FusionMissingness.USE_DECLARED_FALLBACK,
            "standardized fallback requires explicit normalized bridge (unsupported)",
        )
        require(
            self.missingness is not FusionMissingness.DROP_AND_RENORMALIZE
            or self.weight_policy is FusionWeights.SIMPLEX
            and not learned,
            "drop/renormalize fixed simplex only",
        )
        require(
            (self.fallback_source_id is not None)
            == (self.missingness is FusionMissingness.USE_DECLARED_FALLBACK),
            "declared fallback identity required",
        )
        if self.fallback_source_id:
            validate_fingerprint(self.fallback_source_id, "fus_source")
            require(
                self.fallback_source_id not in self.source_ids,
                "fallback must be distinct from contributor set",
            )
        if self.source_selection_result_id:
            validate_fingerprint(self.source_selection_result_id, "sel_result")
