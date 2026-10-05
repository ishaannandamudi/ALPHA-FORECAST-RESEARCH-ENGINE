"""Identity-bearing windows, data criteria and fixed interpretable fitting policy."""

from dataclasses import dataclass

from afre.cross_sectional.definitions import ScoreSpec
from afre.cross_sectional.schema import ScoreSource
from afre.event_conditioned.schema import (
    EVENT_IMPLEMENTATION,
    EventAnchor,
    EventClass,
    EventModelFamily,
    EventOverlapPolicy,
    EventRelation,
    EventScope,
)
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition


@contract("ec_window")
@dataclass(frozen=True, slots=True)
class EventWindowSpec(Artifact):
    target: TargetDefinition
    relation: EventRelation
    anchor: EventAnchor = EventAnchor.OCCURRENCE
    pre_lookback_ns: int = 0
    post_minimum_delay_ns: int = 0
    post_maximum_age_ns: int = 0
    include_minimum: bool = True
    include_maximum: bool = True
    basis: str = "elapsed-UTC-nanoseconds"
    implementation_version: str = EVENT_IMPLEMENTATION

    def _validate(self) -> None:
        require(
            self.basis == "elapsed-UTC-nanoseconds"
            and self.implementation_version == EVENT_IMPLEMENTATION,
            "event window implementation",
        )
        require(self.post_maximum_age_ns >= self.post_minimum_delay_ns, "event window ordering")
        require(
            self.relation is not EventRelation.POST_EVENT_DELAYED
            or self.post_minimum_delay_ns > 0,
            "delayed event window requires positive delay",
        )


@contract("ec_value_rule")
@dataclass(frozen=True, slots=True)
class EventValueRule(Artifact):
    key: str
    semantic_key: tuple[str, str, str, str]
    minimum: float | None = None
    maximum: float | None = None
    use_as_feature: bool = False

    def _validate(self) -> None:
        require(self.key in ("materiality", "novelty", "surprise"), "event value rule key")
        require(
            self.minimum is None or self.maximum is None or self.minimum <= self.maximum,
            "event threshold ordering",
        )


@contract("ec_spec")
@dataclass(frozen=True, slots=True)
class EventConditioningSpec(Artifact):
    base_model_id: str
    window: EventWindowSpec
    classes: tuple[EventClass, ...]
    scopes: tuple[EventScope, ...]
    family: EventModelFamily = EventModelFamily.EVENT_CLASS_OFFSET
    subtypes: tuple[str, ...] = ()
    value_rules: tuple[EventValueRule, ...] = ()
    reaction_specs: tuple[ScoreSpec, ...] = ()
    overlap: EventOverlapPolicy = EventOverlapPolicy.FAIL_ON_MULTIPLE
    minimum_samples: int = 2
    minimum_events: int = 1
    minimum_class_samples: int = 2
    minimum_evaluation_group: int = 2
    materiality_bins: tuple[float, ...] = (0.5,)
    novelty_bins: tuple[float, ...] = (0.5,)
    surprise_bins: tuple[float, ...] = (0.0,)
    age_bins: tuple[int, ...] = (0,)
    seed: int = 0
    qr_tolerance: float = 1e-10
    condition_limit: float = 1e12
    fitting_policy: str = "independent-target-TRAIN-unit-relation-weight-v1"
    calibration_policy: str = "separate-conditioned-state-required-v1"
    implementation_version: str = EVENT_IMPLEMENTATION
    approved_delivery_attestors: tuple[str, ...] = ()

    def _normalize(self) -> None:
        for key in ("classes", "scopes"):
            items = getattr(self, key)
            require(len(set(items)) == len(items), "duplicate event criterion")
            object.__setattr__(self, key, tuple(sorted(items, key=lambda e: e.value)))
        for key in ("subtypes", "approved_delivery_attestors"):
            values = getattr(self, key)
            require(len(set(values)) == len(values), "duplicate event spec evidence")
            object.__setattr__(self, key, tuple(sorted(values)))
        self.ordered("value_rules", "key")
        self.ordered("reaction_specs", "fingerprint")

    def _validate(self) -> None:
        validate_fingerprint(self.base_model_id, "m_artifact")
        require(bool(self.classes) and bool(self.scopes), "empty event criteria")
        require(
            self.minimum_samples >= 2
            and self.minimum_class_samples >= 2
            and self.minimum_evaluation_group >= 2
            and self.minimum_events >= 1,
            "event minimum count",
        )
        require(
            0 < self.qr_tolerance < 1 and self.condition_limit >= 1 and self.seed >= 0,
            "event numerical policy",
        )
        require(
            all(r.source is ScoreSource.EXTERNAL_SIGNAL for r in self.reaction_specs),
            "reaction inputs require neutral external signals",
        )
        features = {r.key for r in self.value_rules if r.use_as_feature}
        require(
            self.family is not EventModelFamily.MATERIALITY_LINEAR
            or features == {"materiality"},
            "materiality model requires exact feature",
        )
        require(
            self.family is not EventModelFamily.SURPRISE_LINEAR or features == {"surprise"},
            "surprise model requires exact feature",
        )
        require(
            self.family is not EventModelFamily.EVENT_CLASS_OFFSET
            or not features
            and not self.reaction_specs,
            "class offset has no continuous features",
        )
        require(
            self.family is EventModelFamily.EVENT_FEATURE_LINEAR or not self.reaction_specs,
            "reaction coefficients require feature-linear model",
        )
        require(
            self.family is not EventModelFamily.EVENT_FEATURE_LINEAR
            or bool(features or self.reaction_specs),
            "feature-linear model has no features",
        )
        for values in (
            self.materiality_bins,
            self.novelty_bins,
            self.surprise_bins,
            self.age_bins,
        ):
            require(tuple(sorted(set(values))) == values, "event bucket ordering")
        require(
            self.fitting_policy == "independent-target-TRAIN-unit-relation-weight-v1"
            and self.calibration_policy == "separate-conditioned-state-required-v1"
            and self.implementation_version == EVENT_IMPLEMENTATION,
            "event policy version",
        )
