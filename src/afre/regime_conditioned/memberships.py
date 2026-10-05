"""Hard identity and complete ordered soft vectors; no normalization or argmax."""

from dataclasses import dataclass
from math import fsum

from afre.regime_conditioned.schema import RegimeMembershipKind
from afre.schema import Artifact, contract, require


@contract("rc_membership")
@dataclass(frozen=True, slots=True)
class RegimeMembership(Artifact):
    kind: RegimeMembershipKind
    states: tuple[str, ...]
    hard_state: str | None = None
    probabilities: tuple[tuple[str, float], ...] = ()
    tolerance: float = 1e-12
    normalization_policy: str = "reject-unscaled-v1"

    def _validate(self) -> None:
        require(
            bool(self.states) and len(set(self.states)) == len(self.states),
            "regime states unique and ordered",
        )
        require(
            0 < self.tolerance <= 1e-10 and self.normalization_policy == "reject-unscaled-v1",
            "regime probability policy",
        )
        if self.kind is RegimeMembershipKind.HARD:
            require(
                self.hard_state in self.states and not self.probabilities,
                "hard regime requires one exact state",
            )
        else:
            require(
                self.hard_state is None
                and tuple(s for s, _ in self.probabilities) == self.states
                and all(0 <= p <= 1 for _, p in self.probabilities)
                and abs(fsum(p for _, p in self.probabilities) - 1.0) <= self.tolerance,
                "soft regime exact ordering/probability sum",
            )

    @property
    def weights(self) -> tuple[float, ...]:
        return (
            tuple(float(s == self.hard_state) for s in self.states)
            if self.kind is RegimeMembershipKind.HARD
            else tuple(p for _, p in self.probabilities)
        )


def effective_support(weights: tuple[float, ...]) -> float:
    total, squares = fsum(weights), fsum(w * w for w in weights)
    return total * total / squares if squares else 0.0
