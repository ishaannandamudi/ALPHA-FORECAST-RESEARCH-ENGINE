"""Exact target/base/taxonomy and fixed TRAIN, fallback and numerical policies."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.regime_conditioned.schema import (
    REGIME_IMPLEMENTATION,
    RegimeFallback,
    RegimeMatchPolicy,
    RegimeMembershipKind,
    RegimeModelFamily,
    RegimeScope,
)
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition


@contract("rc_spec")
@dataclass(frozen=True, slots=True)
class RegimeConditioningSpec(Artifact):
    base_model_id: str
    target: TargetDefinition
    taxonomy_id: str
    scope: RegimeScope
    family: RegimeModelFamily = RegimeModelFamily.REGIME_RESIDUAL_OFFSET
    allowed_memberships: tuple[RegimeMembershipKind, ...] = (RegimeMembershipKind.HARD,)
    matching: RegimeMatchPolicy = RegimeMatchPolicy.LATEST_AVAILABLE
    maximum_age_ns: int = 0
    minimum_samples: int = 2
    minimum_state_samples: int = 2
    minimum_effective_support: float = 2.0
    minimum_evaluation_group: int = 2
    fallback: RegimeFallback = RegimeFallback.USE_BASE
    transition_recent_ns: int = 0
    low_confidence_threshold: float = 0.6
    seed: int = 0
    fitting_policy: str = "exact-TRAIN-fitted-residuals-v1"
    weighting_policy: str = "probability-weighted-state-mean-v1"
    calibration_policy: str = "separate-regime-calibration-required-v1"
    implementation_version: str = REGIME_IMPLEMENTATION
    approved_delivery_attestors: tuple[str, ...] = ()
    event_model_id: str | None = None
    history_policy: str = "latest-causal-revision-per-asof-v1"

    def _normalize(self) -> None:
        for key in ("allowed_memberships", "approved_delivery_attestors"):
            values = getattr(self, key)
            require(len(set(values)) == len(values), "duplicate regime spec policy")
            object.__setattr__(self, key, tuple(sorted(values, key=str)))

    def _validate(self) -> None:
        validate_fingerprint(self.base_model_id, "m_artifact")
        validate_fingerprint(self.taxonomy_id, "rc_taxonomy")
        if self.event_model_id:
            validate_fingerprint(self.event_model_id, "ec_model")
            require(
                self.family is RegimeModelFamily.REGIME_TARGET_MEAN,
                "event composition supports target mean only",
            )
        require(bool(self.allowed_memberships), "empty regime membership policy")
        require(
            self.family is RegimeModelFamily.SOFT_REGIME_WEIGHTED_OFFSET
            or self.allowed_memberships == (RegimeMembershipKind.HARD,),
            "hard model cannot collapse soft memberships",
        )
        require(
            self.minimum_samples >= 2
            and self.minimum_state_samples >= 2
            and self.minimum_effective_support >= 1
            and self.minimum_evaluation_group >= 2,
            "regime minimum counts",
        )
        require(
            0 < self.low_confidence_threshold <= 1 and self.seed >= 0, "regime numerical policy"
        )
        require(
            self.fitting_policy == "exact-TRAIN-fitted-residuals-v1"
            and self.weighting_policy == "probability-weighted-state-mean-v1"
            and self.calibration_policy == "separate-regime-calibration-required-v1"
            and self.implementation_version == REGIME_IMPLEMENTATION,
            "regime policy version",
        )
        require(
            self.history_policy == "latest-causal-revision-per-asof-v1", "regime history policy"
        )
