"""Forecast origin metadata; no forecast generation."""

from dataclasses import dataclass

from afre.ids import InstrumentId, validate_fingerprint
from afre.schema import Artifact, contract, require


@contract("forecast_origin")
@dataclass(frozen=True, slots=True)
class ForecastOrigin(Artifact):
    instrument: InstrumentId
    timestamp_ns: int
    availability_cutoff_ns: int
    market_session_id: str
    build_context: str
    universe_id: str

    def _validate(self) -> None:
        require(self.availability_cutoff_ns <= self.timestamp_ns, "cutoff after origin")
        validate_fingerprint(self.universe_id, "universe_manifest")
