"""Research opportunity counts and explicitly unsupported deflated portfolio statistics."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.multiple_testing.schema import EvidenceState
from afre.schema import Artifact, contract, require


@contract("mt_overfitting")
@dataclass(frozen=True, slots=True)
class ResearchOverfittingDiagnostic(Artifact):
    registry_id: str
    planned_count: int
    completed_count: int
    failed_count: int
    adaptive_count: int
    unknown_count: int
    opportunity_counts: tuple[tuple[str, int], ...]
    repeated_evaluation_counts: tuple[tuple[str, int], ...]
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "opportunity_counts", tuple(sorted(self.opportunity_counts)))
        object.__setattr__(
            self, "repeated_evaluation_counts", tuple(sorted(self.repeated_evaluation_counts))
        )

    def _validate(self) -> None:
        validate_fingerprint(self.registry_id, "mt_registry")
        require(
            all(
                0 <= n <= 2000
                for n in (
                    self.planned_count,
                    self.completed_count,
                    self.failed_count,
                    self.adaptive_count,
                    self.unknown_count,
                )
            ),
            "opportunity count bounds",
        )


@contract("mt_deflated")
@dataclass(frozen=True, slots=True)
class DeflatedPerformanceDiagnostic(Artifact):
    registry_id: str
    state: EvidenceState
    reason: str
    available_ns: int
    value: float | None = None
    method: str = "unsupported-without-justified-standardized-series-v1"

    def _validate(self) -> None:
        validate_fingerprint(self.registry_id, "mt_registry")
        require(
            self.state is EvidenceState.UNSUPPORTED
            and self.value is None
            and self.reason
            == "no-portfolio-return-series-or-justified-generic-deflation-contract"
            and self.method == "unsupported-without-justified-standardized-series-v1",
            "no manufactured Sharpe/deflation",
        )
