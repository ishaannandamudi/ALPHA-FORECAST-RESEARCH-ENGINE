"""Exact existing typed horizons; comparable sorting or supplied canonical order."""

from dataclasses import dataclass

from afre.horizons import ForecastHorizon, HorizonBasis
from afre.multihorizon.schema import IMPLEMENTATION_VERSION, HorizonOrder
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition


@contract("mh_horizon_set")
@dataclass(frozen=True, slots=True)
class HorizonSet(Artifact):
    targets: tuple[TargetDefinition, ...]
    ordering: HorizonOrder = HorizonOrder.COMPARABLE_DURATION
    implementation_version: str = IMPLEMENTATION_VERSION

    def _normalize(self) -> None:
        require(0 < len(self.targets) <= 64, "horizon set size")
        horizons = tuple(t.horizon for t in self.targets)
        require(len(set(horizons)) == len(horizons), "duplicate semantic horizon")
        if self.ordering is HorizonOrder.COMPARABLE_DURATION:
            first = self.targets[0]
            require(
                all(
                    (
                        t.horizon.basis,
                        t.calendar_id,
                        t.bar_definition,
                        t.horizon.endpoint,
                        t.session_policy,
                    )
                    == (
                        first.horizon.basis,
                        first.calendar_id,
                        first.bar_definition,
                        first.horizon.endpoint,
                        first.session_policy,
                    )
                    for t in self.targets
                ),
                "incomparable horizons require explicit canonical order",
            )
            object.__setattr__(
                self,
                "targets",
                tuple(
                    sorted(
                        self.targets,
                        key=lambda t: (
                            t.horizon.duration_ns
                            if t.horizon.basis is HorizonBasis.ELAPSED_TIME
                            else t.horizon.count or 0
                        ),
                    )
                ),
            )

    def _validate(self) -> None:
        require(self.implementation_version == IMPLEMENTATION_VERSION, "horizon set version")

    @property
    def horizons(self) -> tuple[ForecastHorizon, ...]:
        return tuple(t.horizon for t in self.targets)

    def target_for(self, horizon: ForecastHorizon) -> TargetDefinition:
        for target in self.targets:
            if target.horizon == horizon:
                return target
        raise KeyError(horizon.fingerprint)
