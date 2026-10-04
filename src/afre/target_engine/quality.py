"""Independent quality dimensions, rather than an opaque confidence score."""

from dataclasses import dataclass

from afre.features import DataQuality
from afre.schema import Artifact, contract, require
from afre.target_engine.schema import TargetQualityFlag


@contract("target_quality")
@dataclass(frozen=True, slots=True)
class TargetQuality(Artifact):
    source_quality: DataQuality
    flags: tuple[TargetQualityFlag, ...] = ()
    expected_observations: int = 0
    present_observations: int = 0

    def _normalize(self) -> None:
        require(len(set(self.flags)) == len(self.flags), "duplicate target quality flag")
        object.__setattr__(
            self, "flags", tuple(sorted(self.flags, key=lambda flag: flag.value))
        )

    def _validate(self) -> None:
        require(
            0 <= self.present_observations <= self.expected_observations,
            "invalid target path coverage",
        )
