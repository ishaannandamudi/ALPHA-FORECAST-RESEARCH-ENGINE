"""Provider-neutral six-clock cost and liquidity observations, never upstream backdating."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.costs.schema import (
    CostComponentType,
    CostInputRole,
    CostQuality,
    CostTiming,
    CostUnit,
)
from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.ids import InstrumentId
from afre.schema import Artifact, contract, require

if TYPE_CHECKING:
    from afre.costs.definitions import CostScenario
    from afre.costs.repository import CostResearchRepository
    from afre.forecast import ForecastOrigin


@contract("cost_input")
@dataclass(frozen=True, slots=True)
class CostInputReference(Artifact):
    component: CostComponentType
    role: CostInputRole
    provider: str
    version: str
    provider_schema: str
    source: SourceReference
    security: InstrumentId
    unit: CostUnit
    currency: str
    as_of_ns: int
    clocks: AvailabilityEvidence
    quality: CostQuality
    value: float | None
    venue: str | None = None
    revision: str = "1"
    horizon_id: str | None = None
    included_components: tuple[CostComponentType, ...] = ()

    def _normalize(self) -> None:
        require(
            len(self.included_components) == len(set(self.included_components)),
            "duplicate provider embedded category",
        )
        object.__setattr__(
            self,
            "included_components",
            tuple(sorted(self.included_components, key=lambda c: c.value)),
        )

    def _validate(self) -> None:
        from afre.ids import validate_fingerprint

        if self.horizon_id:
            validate_fingerprint(self.horizon_id, "horizon")
        require(
            self.source.provenance.system == self.provider
            and self.source.provenance.source_version == self.version,
            "cost input provider/version",
        )
        require(
            (self.value is not None)
            == (self.quality in (CostQuality.VALID, CostQuality.STALE, CostQuality.DEGRADED)),
            "cost input quality/value",
        )
        require(self.value is None or self.value >= 0, "nonnegative cost/liquidity magnitude")
        if self.role in (CostInputRole.BID, CostInputRole.ASK, CostInputRole.REFERENCE_PRICE):
            require(
                self.unit is CostUnit.PRICE and (self.value is None or self.value > 0),
                "price input units/value",
            )
        if self.role is CostInputRole.REFERENCE_NOTIONAL:
            require(
                self.unit is CostUnit.CURRENCY_TOTAL and (self.value is None or self.value > 0),
                "reference notional units/value",
            )
        if self.role is CostInputRole.AVAILABLE_VOLUME:
            require(
                self.unit is CostUnit.UNIT_QUANTITY
                and self.horizon_id is not None
                and (self.value is None or self.value > 0),
                "available volume units/value",
            )
        if self.role is CostInputRole.MODEL_VALUE:
            require(self.unit is not CostUnit.UNIT_QUANTITY, "quantity is not a cost rate")
            require(
                self.component in self.included_components,
                "provider must declare included cost categories",
            )
        else:
            require(not self.included_components, "quote/liquidity has no embedded costs")
        if self.clocks.historical_delivery:
            p = self.clocks.historical_delivery
            require(
                p.source_id == self.source.fingerprint and p.entity == self.security,
                "cost historical delivery exact source/security",
            )


def input_reason(
    repo: "CostResearchRepository",
    value: CostInputReference,
    scenario: "CostScenario",
    origin: "ForecastOrigin",
    constructed_ns: int,
) -> str | None:
    repo.resolve(SourceReference, value.source.fingerprint)
    require(
        value.security == origin.instrument and value.currency == scenario.currency,
        "cost input exact security/currency",
    )
    require(
        value.horizon_id is None or value.horizon_id == scenario.target.horizon.fingerprint,
        "cost/liquidity horizon applicability",
    )
    require(
        constructed_ns >= value.clocks.afre_computed_ns,
        "actual cost construction precedes actual ingestion/computation",
    )
    proof = value.clocks.historical_delivery
    if proof:
        repo.get_any(proof.fingerprint)
        require(
            proof.attestor in scenario.approved_delivery_attestors,
            "unapproved cost historical delivery evidence",
        )
    if value.quality is not CostQuality.VALID and not (
        scenario.allow_degraded and value.quality is CostQuality.DEGRADED
    ):
        return "cost-quality:" + str(value.quality.value)
    if scenario.timing is CostTiming.HISTORICAL_CAUSAL and (
        value.clocks.final_available_ns > origin.availability_cutoff_ns
        or value.as_of_ns > origin.timestamp_ns
    ):
        return "cost-not-known-at-origin"
    if value.clocks.final_available_ns > constructed_ns:
        return "cost-not-available-at-construction"
    if (
        origin.timestamp_ns >= value.as_of_ns
        and origin.timestamp_ns - value.as_of_ns > scenario.maximum_input_age_ns
    ):
        return "cost-input-stale-by-declared-age"
    return None
