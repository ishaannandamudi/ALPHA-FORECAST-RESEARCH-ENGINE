"""Explicit semantic features, ordered transforms and fixed research model specifications."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.nonlinear.schema import (
    NONLINEAR_IMPLEMENTATION,
    DenominatorPolicy,
    InteractionMissingPolicy,
    InteractionTransform,
    KnotPolicy,
    NonlinearFamily,
    NonlinearMissingPolicy,
    NonlinearPreprocessing,
    ScalarSourceKind,
)
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition


@contract("nl_feature")
@dataclass(frozen=True, slots=True)
class ScalarFeatureDefinition(Artifact):
    kind: ScalarSourceKind
    source_key: tuple[str, ...]
    selector: str
    unit: str

    def _validate(self) -> None:
        require(
            bool(self.source_key) and len(self.source_key) <= 16, "scalar semantic key bound"
        )
        require(
            not any(
                k.lower()
                in {
                    "target",
                    "orders",
                    "positions",
                    "execution",
                    "live_inventory",
                    "pending_orders",
                }
                for key in self.source_key
                for k in key.split(".")
            ),
            "forbidden scalar source semantics",
        )


@contract("nl_transform_parameters")
@dataclass(frozen=True, slots=True)
class TransformParameters(Artifact):
    denominator: DenominatorPolicy | None = None
    epsilon: float | None = None
    clip_lower: float | None = None
    clip_upper: float | None = None
    knot_policy: KnotPolicy | None = None
    knots: tuple[float, ...] = ()
    quantile_levels: tuple[float, ...] = ()
    ordinates: tuple[float, ...] = ()

    def _validate(self) -> None:
        require(self.epsilon is None or self.epsilon > 0, "positive denominator epsilon")
        require(
            len(self.knots) <= 16
            and len(self.quantile_levels) <= 16
            and len(self.ordinates) <= 16,
            "piecewise knot bound",
        )
        require(
            all(a < b for a, b in zip(self.knots, self.knots[1:], strict=False)),
            "ordered unique knots",
        )
        require(
            all(0 <= x <= 1 for x in self.quantile_levels)
            and all(
                a < b
                for a, b in zip(self.quantile_levels, self.quantile_levels[1:], strict=False)
            ),
            "ordered quantile levels",
        )


def output_unit(
    transform: InteractionTransform, features: tuple[ScalarFeatureDefinition, ...]
) -> str:
    if transform is InteractionTransform.PRODUCT:
        features = tuple(sorted(features, key=lambda f: f.fingerprint))
    units = tuple(f.unit for f in features)
    if transform is InteractionTransform.PRODUCT:
        return "(" + "*".join(units) + ")"
    if transform is InteractionTransform.RATIO:
        return "1" if units[0] == units[1] else f"({units[0]}/{units[1]})"
    if transform in (InteractionTransform.SQUARE, InteractionTransform.CUBE):
        return f"({units[0]}^{2 if transform is InteractionTransform.SQUARE else 3})"
    if transform is InteractionTransform.LOG1P_SIGNED:
        require(units == ("1",), "signed log requires dimensionless input")
    if transform in (InteractionTransform.DIFFERENCE, InteractionTransform.ABS_DIFFERENCE):
        require(units[0] == units[1], "difference unit mismatch")
    return units[0]


@contract("nl_interaction")
@dataclass(frozen=True, slots=True)
class InteractionDefinition(Artifact):
    interaction_id: str
    inputs: tuple[ScalarFeatureDefinition, ...]
    transform: InteractionTransform
    parameters: TransformParameters
    output_name: str
    unit: str
    missing_policy: InteractionMissingPolicy = InteractionMissingPolicy.FAIL
    fallback_value: float | None = None
    availability_policy: str = "max-input-transform-and-actual-computation-v1"
    implementation_version: str = NONLINEAR_IMPLEMENTATION

    def _normalize(self) -> None:
        if self.transform in (
            InteractionTransform.PRODUCT,
            InteractionTransform.ABS_DIFFERENCE,
        ):
            object.__setattr__(
                self, "inputs", tuple(sorted(self.inputs, key=lambda f: f.fingerprint))
            )

    def _validate(self) -> None:
        binary = self.transform in (
            InteractionTransform.PRODUCT,
            InteractionTransform.RATIO,
            InteractionTransform.DIFFERENCE,
            InteractionTransform.ABS_DIFFERENCE,
        )
        require(len(self.inputs) == (2 if binary else 1), "transform arity")
        require(
            self.unit == output_unit(self.transform, self.inputs),
            "explicit transform output unit",
        )
        p = self.parameters
        require(
            (self.fallback_value is not None)
            == (self.missing_policy is InteractionMissingPolicy.DECLARED_FALLBACK),
            "declared fallback",
        )
        if self.transform is InteractionTransform.RATIO:
            require(
                p.denominator is not None
                and (p.epsilon is not None)
                == (p.denominator is DenominatorPolicy.EPSILON_FLOOR),
                "ratio denominator policy",
            )
        else:
            require(
                p.denominator is None and p.epsilon is None, "unused denominator parameters"
            )
        if self.transform is InteractionTransform.CLIPPED_LINEAR:
            require(
                p.clip_lower is not None
                and p.clip_upper is not None
                and p.clip_lower < p.clip_upper,
                "explicit clipping interval",
            )
        else:
            require(p.clip_lower is None and p.clip_upper is None, "unused clipping parameters")
        if self.transform is InteractionTransform.PIECEWISE_LINEAR:
            require(p.knot_policy is not None, "explicit knot policy")
            points = p.knots if p.knot_policy is KnotPolicy.FIXED else p.quantile_levels
            require(2 <= len(points) == len(p.ordinates), "piecewise points/ordinates")
            require(
                not (p.quantile_levels if p.knot_policy is KnotPolicy.FIXED else p.knots),
                "unused piecewise points",
            )
        else:
            require(
                p.knot_policy is None
                and not p.knots
                and not p.quantile_levels
                and not p.ordinates,
                "unused piecewise parameters",
            )
        require(
            self.availability_policy == "max-input-transform-and-actual-computation-v1"
            and self.implementation_version == NONLINEAR_IMPLEMENTATION,
            "interaction implementation",
        )

    @property
    def semantic_key(self) -> tuple[object, ...]:
        return (
            self.inputs,
            self.transform,
            self.parameters,
            self.missing_policy,
            self.fallback_value,
        )


@contract("nl_set")
@dataclass(frozen=True, slots=True)
class InteractionSet(Artifact):
    definitions: tuple[InteractionDefinition, ...]
    target: TargetDefinition
    maximum_count: int = 128
    implementation_version: str = NONLINEAR_IMPLEMENTATION

    def _normalize(self) -> None:
        self.ordered("definitions", "interaction_id")

    def _validate(self) -> None:
        require(
            0 < len(self.definitions) <= self.maximum_count <= 128, "interaction count bound"
        )
        require(
            len({d.semantic_key for d in self.definitions}) == len(self.definitions),
            "duplicate semantic interaction",
        )
        require(
            len({d.output_name for d in self.definitions}) == len(self.definitions),
            "duplicate output column",
        )
        require(
            self.implementation_version == NONLINEAR_IMPLEMENTATION,
            "interaction set implementation",
        )

    @property
    def features(self) -> tuple[ScalarFeatureDefinition, ...]:
        values = {f.fingerprint: f for d in self.definitions for f in d.inputs}
        return tuple(values[i] for i in sorted(values))


@contract("nl_tree_parameters")
@dataclass(frozen=True, slots=True)
class TreeParameters(Artifact):
    maximum_depth: int = 2
    minimum_leaf_count: int = 2
    maximum_candidates: int = 32
    minimum_improvement: float = 0.0
    split_method: str = "bounded-unique-midpoints-v1"
    tie_rule: str = "SSE-feature-identity-threshold-left-leq-v1"

    def _validate(self) -> None:
        require(
            1 <= self.maximum_depth <= 4
            and self.minimum_leaf_count >= 1
            and 1 <= self.maximum_candidates <= 64
            and self.minimum_improvement >= 0,
            "tree parameter bounds",
        )
        require(
            self.split_method == "bounded-unique-midpoints-v1"
            and self.tie_rule == "SSE-feature-identity-threshold-left-leq-v1",
            "tree split implementation",
        )


@contract("nl_spec")
@dataclass(frozen=True, slots=True)
class NonlinearModelSpec(Artifact):
    interaction_set: InteractionSet
    family: NonlinearFamily
    original_features: tuple[ScalarFeatureDefinition, ...]
    fold_id: str
    cutoff_ns: int
    seed: int
    preprocessing: NonlinearPreprocessing = NonlinearPreprocessing.NONE
    missing_policy: NonlinearMissingPolicy = NonlinearMissingPolicy.FAIL
    tree: TreeParameters | None = None
    ridge_penalty: float = 0.0
    tolerance: float = 1e-12
    condition_limit: float = 1e12
    approved_delivery_attestors: tuple[str, ...] = ()
    implementation_version: str = NONLINEAR_IMPLEMENTATION

    def _normalize(self) -> None:
        self.ordered("original_features", "fingerprint")
        require(
            len(set(self.approved_delivery_attestors)) == len(self.approved_delivery_attestors),
            "duplicate approved attestors",
        )
        object.__setattr__(
            self, "approved_delivery_attestors", tuple(sorted(self.approved_delivery_attestors))
        )

    def _validate(self) -> None:
        validate_fingerprint(self.fold_id, "r_fold")
        require(
            0 <= self.seed <= 2**32 - 1
            and self.ridge_penalty >= 0
            and 0 < self.tolerance < 1
            and self.condition_limit >= 1,
            "model numerical policy",
        )
        require(
            (self.tree is not None) == (self.family is NonlinearFamily.SHALLOW_REGRESSION_TREE),
            "tree family parameters",
        )
        require(
            self.family is not NonlinearFamily.LINEAR_ON_INTERACTIONS
            or not self.original_features,
            "interaction-only model has no originals",
        )
        require(
            self.family is not NonlinearFamily.LINEAR_PLUS_INTERACTIONS
            or bool(self.original_features),
            "linear plus interactions requires original columns",
        )
        require(
            self.family is not NonlinearFamily.SHALLOW_REGRESSION_TREE
            or self.ridge_penalty == 0
            and self.preprocessing is NonlinearPreprocessing.NONE,
            "tree uses raw columns without ridge",
        )
        require(self.implementation_version == NONLINEAR_IMPLEMENTATION, "model implementation")

    @property
    def target(self) -> TargetDefinition:
        return self.interaction_set.target

    @property
    def features(self) -> tuple[ScalarFeatureDefinition, ...]:
        values = {
            f.fingerprint: f for f in (*self.interaction_set.features, *self.original_features)
        }
        return tuple(values[i] for i in sorted(values))

    @property
    def columns(self) -> tuple[str, ...]:
        return (
            *tuple(f.fingerprint for f in self.original_features),
            *tuple(d.fingerprint for d in self.interaction_set.definitions),
        )
