"""Exact expert composition and a single predeclared convex TRAIN objective."""

from dataclasses import dataclass
from math import fsum

from afre.ids import validate_fingerprint
from afre.mixture.experts import ExpertReference
from afre.mixture.schema import MIXTURE_IMPLEMENTATION, ExpertMissingPolicy, ExpertOutput
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition


def validate_weights(
    weights: tuple[tuple[str, float], ...], ids: tuple[str, ...], tolerance: float = 1e-12
) -> None:
    require(0 < tolerance <= 1e-12, "mixture weight tolerance")
    require(tuple(i for i, _ in weights) == ids, "exact ordered expert weights required")
    require(
        all(0 <= w <= 1 + tolerance for _, w in weights)
        and abs(fsum(w for _, w in weights) - 1) <= tolerance,
        "nonnegative normalized expert weights required",
    )


@contract("mix_set")
@dataclass(frozen=True, slots=True)
class ExpertSet(Artifact):
    experts: tuple[ExpertReference, ...]
    target: TargetDefinition
    missing_policy: ExpertMissingPolicy = ExpertMissingPolicy.FAIL
    fallback_id: str | None = None
    maximum_age_ns: int = 0
    approved_delivery_attestors: tuple[str, ...] = ()
    implementation_version: str = MIXTURE_IMPLEMENTATION

    def _normalize(self) -> None:
        self.ordered("experts", "fingerprint")
        require(
            len(set(self.approved_delivery_attestors)) == len(self.approved_delivery_attestors),
            "duplicate delivery attestor",
        )
        object.__setattr__(
            self, "approved_delivery_attestors", tuple(sorted(self.approved_delivery_attestors))
        )

    def _validate(self) -> None:
        require(bool(self.experts), "empty expert set")
        require(
            len({e.expert_id for e in self.experts}) == len(self.experts)
            and len({(e.kind, e.model_id, e.output) for e in self.experts})
            == len(self.experts),
            "duplicate semantic expert",
        )
        require(
            all(
                e.target == self.target and e.output is self.experts[0].output
                for e in self.experts
            ),
            "exact expert target/horizon/output mismatch",
        )
        require(
            self.experts[0].output is not ExpertOutput.CALIBRATED_PROBABILISTIC,
            "calibrated mixtures unsupported",
        )
        require(
            (self.fallback_id is not None)
            == (self.missing_policy is ExpertMissingPolicy.USE_DECLARED_FALLBACK),
            "explicit fallback policy/identity required",
        )
        if self.fallback_id:
            require(
                self.fallback_id in tuple(e.fingerprint for e in self.experts),
                "fallback must be exact set member",
            )
        require(
            self.implementation_version == MIXTURE_IMPLEMENTATION,
            "unsupported expert composition version",
        )

    @property
    def expert_ids(self) -> tuple[str, ...]:
        return tuple(e.fingerprint for e in self.experts)


@contract("mix_fixed_gate")
@dataclass(frozen=True, slots=True)
class FixedGateSpec(Artifact):
    expert_set: ExpertSet
    weights: tuple[tuple[str, float], ...]
    tolerance: float = 1e-12
    available_ns: int = 0
    normalization_policy: str = "reject-unscaled-v1"
    implementation_version: str = MIXTURE_IMPLEMENTATION

    def _normalize(self) -> None:
        object.__setattr__(self, "weights", tuple(sorted(self.weights)))

    def _validate(self) -> None:
        validate_weights(self.weights, self.expert_set.expert_ids, self.tolerance)
        require(
            self.normalization_policy == "reject-unscaled-v1"
            and self.implementation_version == MIXTURE_IMPLEMENTATION,
            "unsupported fixed gating policy",
        )


@contract("mix_learned_spec")
@dataclass(frozen=True, slots=True)
class LearnedGateSpec(Artifact):
    expert_set: ExpertSet
    fold_id: str
    cutoff_ns: int
    gating_feature_ids: tuple[str, ...] = ()
    minimum_samples: int = 2
    ridge_penalty: float = 0.0
    maximum_iterations: int = 10_000
    convergence_tolerance: float = 1e-10
    seed: int = 0
    objective: str = "mean-squared-error-simplex-v1"
    intercept_policy: str = "no-intercept"
    feature_policy: str = "causal-audit-only-no-contextual-weighting-v1"
    normalization_policy: str = "simplex-projection-v1"
    implementation_version: str = MIXTURE_IMPLEMENTATION

    def _normalize(self) -> None:
        require(
            len(set(self.gating_feature_ids)) == len(self.gating_feature_ids),
            "duplicate gating feature definition",
        )
        object.__setattr__(self, "gating_feature_ids", tuple(sorted(self.gating_feature_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.fold_id, "r_fold")
        require(
            self.minimum_samples > 0
            and self.ridge_penalty >= 0
            and 0 < self.maximum_iterations <= 100_000
            and 0 < self.convergence_tolerance <= 1e-4
            and self.seed >= 0,
            "invalid learned gate numerical policy",
        )
        require(
            self.objective == "mean-squared-error-simplex-v1"
            and self.intercept_policy == "no-intercept"
            and self.feature_policy == "causal-audit-only-no-contextual-weighting-v1"
            and self.normalization_policy == "simplex-projection-v1"
            and self.implementation_version == MIXTURE_IMPLEMENTATION,
            "unsupported learned gate objective/policy",
        )
