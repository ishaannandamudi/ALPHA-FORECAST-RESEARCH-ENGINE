"""Provider-neutral data boundary; no executable adapters or source-selected paths."""

from dataclasses import dataclass
from typing import Protocol

from afre.cross_sectional.schema import SignalQuality
from afre.feature_store.models import (
    AvailabilityEvidence,
    FeatureVintage,
    RegisteredFeatureDefinition,
    SourceReference,
)
from afre.feature_store.schema import StoreScope
from afre.features import DataQuality, MissingState, ValueType
from afre.lineage import Scalar
from afre.schema import Artifact, contract, require
from afre.universe.identity import StableSecurityId


@contract("cs_external_signal")
@dataclass(frozen=True, slots=True)
class ExternalSignal(Artifact):
    provider_name: str
    provider_version: str
    provider_schema: str
    security: StableSecurityId
    signal_name: str
    signal_version: str
    signal_semantics: str
    as_of_ns: int
    clocks: AvailabilityEvidence
    value: Scalar | None
    unit: str
    quality: SignalQuality
    source: SourceReference
    venue_id: str | None = None

    def _validate(self) -> None:
        require(
            (self.value is not None)
            == (self.quality in (SignalQuality.VALID, SignalQuality.DEGRADED)),
            "signal quality/value",
        )
        require(self.as_of_ns <= self.clocks.final_available_ns, "signal future as-of")
        forbidden = {
            "order_id",
            "live_inventory",
            "position_size",
            "pending_orders",
            "execution_decision",
        }
        require(
            not forbidden.intersection(self.signal_name.lower().split(".")),
            "execution fields are not predictive signals",
        )
        require(
            self.source.provenance.system == self.provider_name
            and self.source.provenance.source_version == self.provider_version,
            "provider provenance mismatch",
        )
        delivery = self.clocks.historical_delivery
        require(
            delivery is None
            or (
                delivery.source_id == self.source.fingerprint
                and delivery.entity == self.security.instrument
            ),
            "signal delivery evidence",
        )

    @property
    def semantic_key(self) -> tuple[str, ...]:
        return (
            self.provider_name,
            self.provider_version,
            self.provider_schema,
            self.signal_name,
            self.signal_version,
            self.signal_semantics,
            self.unit,
        )


class ExternalSignalProvider(Protocol):
    def signals_as_of(
        self, securities: tuple[StableSecurityId, ...], cutoff_ns: int, signal_name: str
    ) -> tuple[ExternalSignal, ...]: ...


def signal_feature(
    signal: ExternalSignal, definition: RegisteredFeatureDefinition
) -> FeatureVintage:
    """Explicit conversion to ordinary AFRE-1 data, including categorical state."""
    require(
        definition.scope is StoreScope.SECURITY
        and definition.definition.unit == signal.unit
        and definition.definition.version == signal.signal_version
        and definition.definition.name == signal.signal_name,
        "external feature definition semantics mismatch",
    )
    type_key = {
        ValueType.NUMBER: (int, float),
        ValueType.INTEGER: (int,),
        ValueType.BOOLEAN: (bool,),
        ValueType.TEXT: (str,),
    }
    require(
        signal.value is None
        or type(signal.value) in type_key[definition.definition.value_type],
        "external feature value type",
    )
    states = {
        SignalQuality.VALID: MissingState.PRESENT,
        SignalQuality.DEGRADED: MissingState.UNKNOWN,
        SignalQuality.STALE: MissingState.STALE,
        SignalQuality.MISSING: MissingState.MISSING,
        SignalQuality.UNSUPPORTED: MissingState.NOT_APPLICABLE,
        SignalQuality.INVALID: MissingState.INVALID,
    }
    state = states[signal.quality]
    return FeatureVintage(
        definition,
        signal.security.instrument,
        signal.as_of_ns,
        signal.clocks,
        signal.source,
        signal.value if state is MissingState.PRESENT else None,
        state,
        DataQuality.VERIFIED if state is MissingState.PRESENT else DataQuality.UNVERIFIED,
    )
