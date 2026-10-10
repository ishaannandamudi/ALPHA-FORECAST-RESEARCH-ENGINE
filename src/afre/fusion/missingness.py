"""Declared fixed-simplex dropping; learned columns never disappear silently."""

from math import fsum

from afre.fusion.artifacts import FusionArtifact, FusionObservation
from afre.fusion.definitions import FusionSpec
from afre.fusion.schema import FusionMissingness
from afre.schema import require


def effective_weights(
    spec: FusionSpec, artifact: FusionArtifact, obs: tuple[FusionObservation, ...]
) -> tuple[tuple[str, float], ...]:
    available = {o.source_id for o in obs if o.value is not None}
    if available == set(spec.source_ids):
        return artifact.weights
    if spec.missingness is FusionMissingness.DROP_AND_RENORMALIZE:
        surviving = tuple((i, w) for i, w in artifact.weights if i in available)
        total = fsum(w for _, w in surviving)
        if total > 0:
            return tuple((i, w / total) for i, w in surviving)
    require(spec.missingness in tuple(FusionMissingness), "missingness policy")
    return ()
