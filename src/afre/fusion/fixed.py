"""Identity-bearing fixed weights; normalization occurs only by declaration."""

from math import fsum

from afre.fusion.definitions import FusionSpec
from afre.fusion.schema import FusionNormalization
from afre.statistical_models.linear_algebra import finite


def fixed_weights(spec: FusionSpec) -> tuple[tuple[str, float], ...]:
    if spec.normalization is FusionNormalization.EXPLICIT_SIMPLEX:
        total = fsum(w for _, w in spec.weights)
        return tuple((i, finite(w / total)) for i, w in spec.weights)
    return spec.weights
