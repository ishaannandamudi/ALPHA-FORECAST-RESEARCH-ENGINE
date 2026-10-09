"""Descriptive effects remain separate from evidence and are never correction-shrunk."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.multiple_testing.schema import EvidenceState
from afre.schema import Artifact, contract, require


@contract("mt_effect")
@dataclass(frozen=True, slots=True)
class EffectSizeResult(Artifact):
    trial_id: str
    hypothesis_id: str
    estimate: float | None
    unit: str
    sample_count: int
    state: EvidenceState
    available_ns: int
    method: str = "descriptive-sample-median-minus-declared-null-v1"
    standard_error: float | None = None
    confidence_interval: tuple[float, float] | None = None

    def _validate(self) -> None:
        validate_fingerprint(self.trial_id, "mt_trial")
        validate_fingerprint(self.hypothesis_id, "mt_hypothesis")
        require(
            (self.estimate is not None) == (self.state is EvidenceState.AVAILABLE)
            and 0 <= self.sample_count <= 2000,
            "effect status/support",
        )
        require(
            self.standard_error is None
            and self.confidence_interval is None
            and self.method == "descriptive-sample-median-minus-declared-null-v1",
            "unimplemented effect SE/CI unsupported",
        )
