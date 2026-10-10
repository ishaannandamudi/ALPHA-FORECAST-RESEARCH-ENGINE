"""Post-hoc uncertainty/stability attachments cannot change forecast weights."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.fusion.artifacts import FusedForecast, FusionObservation
from afre.invariance.artifacts import EnvironmentMetric
from afre.schema import Artifact, contract, require
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository


@contract("fus_metadata")
@dataclass(frozen=True, slots=True)
class FusionMetadata(Artifact):
    forecast_id: str
    diagnostic_ids: tuple[str, ...]
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "diagnostic_ids", tuple(sorted(self.diagnostic_ids)))

    def _validate(self) -> None:
        require(
            0 < len(self.diagnostic_ids) <= 32
            and len(set(self.diagnostic_ids)) == len(self.diagnostic_ids),
            "bounded exact diagnostic attachments",
        )


def validate_metadata(repo: "FusionRepository", value: FusionMetadata) -> None:
    forecast = repo.resolve(FusedForecast, value.forecast_id)
    outputs = {repo.get(FusionObservation, i).output_id for i in forecast.observation_ids}
    require(value.available_ns >= forecast.available_ns, "metadata cannot predate output")
    for i in value.diagnostic_ids:
        raw = repo.get_any(i)
        if isinstance(raw, ForecastUncertaintyDecomposition):
            require(
                raw.forecast_id in outputs
                and raw.sample_id == forecast.sample_id
                and raw.target_id == forecast.target_id
                and raw.available_ns <= value.available_ns,
                "exact source uncertainty metadata",
            )
        else:
            require(
                isinstance(raw, EnvironmentMetric)
                and raw.target_id == forecast.target_id
                and raw.horizon_id == forecast.horizon_id
                and forecast.sample_id in raw.sample_ids
                and bool(outputs.intersection(raw.forecast_ids))
                and raw.available_ns <= value.available_ns,
                "explicit post-hoc stability metadata",
            )
