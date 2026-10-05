"""Transitions over an explicit causal supplied history, never future full duration."""

from math import fsum

from afre.regime_conditioned.artifacts import RegimeTransition
from afre.regime_conditioned.regimes import RegimeSnapshot
from afre.regime_conditioned.schema import RegimeQuality, RegimeStateSemantics
from afre.schema import require


def transition_for(previous: RegimeSnapshot, current: RegimeSnapshot) -> RegimeTransition:
    require(
        previous.taxonomy == current.taxonomy
        and previous.subject == current.subject
        and previous.as_of_ns < current.as_of_ns,
        "regime transition exact ordered stream",
    )
    require(
        all(
            s.semantics is RegimeStateSemantics.FILTERED and s.quality is RegimeQuality.VALID
            for s in (previous, current)
        ),
        "regime transition requires causal valid states",
    )
    return RegimeTransition(
        previous.fingerprint,
        current.fingerprint,
        current.taxonomy.fingerprint,
        previous.membership,
        current.membership,
        current.as_of_ns,
        max(previous.clocks.final_available_ns, current.clocks.final_available_ns),
        previous.membership.kind != current.membership.kind
        or previous.membership.weights != current.membership.weights,
        0.5
        * fsum(
            abs(a - b)
            for a, b in zip(
                previous.membership.weights, current.membership.weights, strict=True
            )
        ),
    )
