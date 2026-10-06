"""Explicit candidate/reference identities and immutable supplied policies; no search."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.orthogonalization.schema import (
    OrthogonalizationMode,
    ProjectionIntercept,
    ProjectionPreprocessing,
    SignalSourceType,
)
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition


@contract("ort_reference")
@dataclass(frozen=True, slots=True)
class SignalReference(Artifact):
    signal_id: str
    source_type: SignalSourceType
    source_key: tuple[str, ...]
    provider: str
    provider_version: str
    semantic_name: str
    semantic_version: str
    unit: str
    selector: str = "value"
    target: TargetDefinition | None = None

    def _validate(self) -> None:
        require(
            bool(self.source_key) and len(self.source_key) <= 12,
            "exact signal semantic source key required",
        )
        require(
            self.selector == "value"
            or self.source_type
            in (SignalSourceType.EVENT, SignalSourceType.REGIME, SignalSourceType.UNCERTAINTY),
            "unsupported signal selector",
        )


@contract("ort_spec")
@dataclass(frozen=True, slots=True)
class OrthogonalizationSpec(Artifact):
    candidate: SignalReference
    references: tuple[SignalReference, ...]
    mode: OrthogonalizationMode
    fold_id: str
    cutoff_ns: int
    target: TargetDefinition
    intercept: ProjectionIntercept = ProjectionIntercept.WITH_INTERCEPT
    preprocessing: ProjectionPreprocessing = ProjectionPreprocessing.NONE
    minimum_samples: int = 3
    tolerance: float = 1e-10
    condition_limit: float = 1e10
    seed: int = 0
    weighting: str = "equal-row-weight-v1"
    implementation_version: str = "TRAIN-pivoted-QR-projection-v1"

    def _normalize(self) -> None:
        self.ordered("references", "fingerprint")

    def _validate(self) -> None:
        validate_fingerprint(self.fold_id, "r_fold")
        require(
            0 < len(self.references) <= 16 and self.candidate not in self.references,
            "explicit distinct reference set",
        )
        require(
            all(
                r.target is None or r.target == self.target
                for r in (self.candidate, *self.references)
            ),
            "predictive signal exact target/horizon",
        )
        require(
            3 <= self.minimum_samples <= 2000
            and 0 < self.tolerance <= 1e-6
            and 1 <= self.condition_limit <= 1e12
            and self.seed >= 0,
            "projection numerical/count policy",
        )
        require(
            self.weighting == "equal-row-weight-v1"
            and self.implementation_version == "TRAIN-pivoted-QR-projection-v1",
            "unsupported projection policy",
        )
