"""Membership sources and eligibility are independent, identity-bearing policies."""

import re
from dataclasses import dataclass

from afre.feature_store.models import RegisteredFeatureDefinition, SourceReference
from afre.feature_store.schema import StoreScope, ValidityRule
from afre.schema import Artifact, contract, require
from afre.universe.calendars import UniverseCalendar
from afre.universe.identity import ListingId
from afre.universe.schema import (
    UNIVERSE_BUILDER_VERSION,
    EligibilityMissingRule,
    SecurityType,
    UniverseSourceKind,
)


@contract("u_eligibility_policy")
@dataclass(frozen=True, slots=True)
class EligibilityPolicy(Artifact):
    security_types: tuple[SecurityType, ...] = (SecurityType.COMMON_STOCK,)
    venues: tuple[str, ...] = ()
    countries: tuple[str, ...] = ()
    currencies: tuple[str, ...] = ()
    selected_listing: ListingId | None = None
    primary_only: bool = True
    require_tradable: bool = True
    require_active_session: bool = False
    include_extended: bool = False
    minimum_listing_sessions: int = 0
    minimum_data_observations: int = 0
    missing_rule: EligibilityMissingRule = EligibilityMissingRule.UNKNOWN
    price_feature: RegisteredFeatureDefinition | None = None
    volume_feature: RegisteredFeatureDefinition | None = None
    price_currency: str | None = None
    minimum_price: float | None = None
    minimum_share_volume: float | None = None
    minimum_mean_dollar_volume: float | None = None
    lookback_ns: int = 1
    minimum_liquidity_observations: int = 1

    def _normalize(self) -> None:
        require(
            len(set(self.security_types)) == len(self.security_types),
            "duplicate security type rule",
        )
        object.__setattr__(
            self, "security_types", tuple(sorted(self.security_types, key=lambda x: x.value))
        )
        for name in ("venues", "countries", "currencies"):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "duplicate eligibility rule")
            object.__setattr__(self, name, tuple(sorted(values)))

    def _validate(self) -> None:
        require(bool(self.security_types), "explicit security types required")
        require(
            self.minimum_listing_sessions >= 0
            and self.minimum_data_observations >= 0
            and self.lookback_ns > 0
            and self.minimum_liquidity_observations > 0,
            "invalid eligibility history policy",
        )
        for value in (
            self.minimum_price,
            self.minimum_share_volume,
            self.minimum_mean_dollar_volume,
        ):
            require(value is None or value >= 0, "negative eligibility threshold")
        require(
            (self.price_feature is not None) == (self.price_currency is not None),
            "price feature requires explicit currency",
        )
        require(
            self.minimum_price is None or self.price_feature is not None,
            "price threshold lacks feature",
        )
        require(
            self.minimum_data_observations == 0 or self.price_feature is not None,
            "history rule lacks price observations",
        )
        require(
            self.minimum_share_volume is None or self.volume_feature is not None,
            "volume threshold lacks feature",
        )
        require(
            self.minimum_mean_dollar_volume is None
            or (self.price_feature is not None and self.volume_feature is not None),
            "dollar volume requires price and share-volume features",
        )
        if self.price_feature is not None and self.volume_feature is not None:
            require(
                self.price_feature.build_context == self.volume_feature.build_context
                and self.price_feature.adjustment == self.volume_feature.adjustment,
                "price/volume build or adjustment mismatch",
            )
        for feature in (self.price_feature, self.volume_feature):
            if feature is not None:
                require(
                    feature.scope is StoreScope.SECURITY
                    and feature.validity_rule is ValidityRule.LAST_OBSERVATION,
                    "eligibility requires security completed-observation features",
                )
        if self.price_feature is not None:
            require(
                self.price_feature.definition.unit == self.price_currency,
                "price feature unit/currency mismatch",
            )
        if self.volume_feature is not None:
            require(
                self.volume_feature.definition.unit == "shares",
                "volume feature must use shares",
            )


@contract("u_definition")
@dataclass(frozen=True, slots=True)
class UniverseDefinition(Artifact):
    name: str
    version: str
    source_kind: UniverseSourceKind
    source: SourceReference
    eligibility: EligibilityPolicy
    calendar: UniverseCalendar
    implementation_version: str = UNIVERSE_BUILDER_VERSION

    def _validate(self) -> None:
        require(
            re.fullmatch(r"universe\.[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*", self.name)
            is not None,
            "universe semantic namespace required",
        )
        for feature in (self.eligibility.price_feature, self.eligibility.volume_feature):
            if feature is not None:
                require(
                    feature.calendar_id == self.calendar.calendar_id,
                    "universe/market calendar mismatch",
                )
        require(
            self.source_kind is not UniverseSourceKind.CURRENT_CONSTITUENTS,
            "current constituents cannot reconstruct historical universes",
        )
