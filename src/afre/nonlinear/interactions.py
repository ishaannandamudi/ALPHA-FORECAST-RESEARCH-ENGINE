"""Target-free exact transform application and input/computation availability floors."""

from typing import TYPE_CHECKING

from afre.nonlinear.artifacts import FittedTransformArtifact, InteractionValue, NonlinearInput
from afre.nonlinear.definitions import InteractionDefinition
from afre.nonlinear.schema import KnotPolicy
from afre.nonlinear.transforms import transform_value
from afre.schema import require

if TYPE_CHECKING:
    from afre.nonlinear.repository import NonlinearRepository


def interaction_for(
    repo: "NonlinearRepository",
    definition: InteractionDefinition,
    inputs: NonlinearInput,
    computed_ns: int,
    state: FittedTransformArtifact | None = None,
) -> InteractionValue:
    mapping = {s.definition.fingerprint: s for s in inputs.scalars}
    require(
        all(f.fingerprint in mapping for f in definition.inputs),
        "interaction required exact source features",
    )
    scalars = tuple(mapping[f.fingerprint] for f in definition.inputs)
    learned = definition.parameters.knot_policy is KnotPolicy.TRAIN_QUANTILES
    require((state is not None) == learned, "interaction exact fitted transform state")
    if state:
        require(state.definition_id == definition.fingerprint, "transform definition mismatch")
    required = max(*(s.available_ns for s in scalars), state.available_ns if state else 0)
    require(computed_ns >= required, "interaction computation precedes source/transform")
    value, fallback = transform_value(
        definition, tuple(s.value for s in scalars), state.knots if state else ()
    )
    return InteractionValue(
        definition.fingerprint,
        tuple(s.fingerprint for s in scalars),
        state.fingerprint if state else None,
        value,
        fallback,
        computed_ns,
        computed_ns,
    )
