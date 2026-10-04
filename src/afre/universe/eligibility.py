"""Deterministic eligibility reasons; membership is never silently discarded."""

import math
from typing import cast

from afre.schema import ContractError
from afre.universe.calendars import UniverseCalendar
from afre.universe.definitions import UniverseDefinition
from afre.universe.lifecycle import LifecycleEvent, SecurityRelationship, TradabilityRecord
from afre.universe.liquidity import observations, usable
from afre.universe.listings import ListingRecord, SymbolAssignment
from afre.universe.membership import MembershipSelection
from afre.universe.models import EligibilityResult
from afre.universe.queries import active_records, precedence, record_candidates
from afre.universe.repository import UniverseRepository
from afre.universe.schema import (
    EligibilityMissingRule,
    LifecycleKind,
    MembershipState,
    TradabilityState,
)
from afre.universe.schema import (
    EligibilityReason as Reason,
)
from afre.universe.schema import (
    EligibilityState as State,
)
from afre.universe.securities import ExternalIdentifier, IssuerRecord, SecurityRecord


def evaluate(
    repository: UniverseRepository, definition: UniverseDefinition, member: MembershipSelection
) -> EligibilityResult:
    policy = definition.eligibility
    security = member.security
    at = member.valid_at_ns
    known = member.known_as_of_ns
    build_id = member.input_build_id
    refs: list[str] = []
    market: list[str] = []
    listing = None
    price = None
    volume = None
    dollar = None
    count = 0
    sessions = 0

    def result(state: State, reason: Reason) -> EligibilityResult:
        return EligibilityResult(
            member,
            state,
            (reason,),
            listing.listing if listing else None,
            tuple(set(refs)),
            tuple(set(market)),
            price,
            volume,
            dollar,
            count,
            sessions,
        )

    def missing(reason: Reason = Reason.MISSING_DATA) -> EligibilityResult:
        return result(
            State.INELIGIBLE
            if policy.missing_rule is EligibilityMissingRule.INELIGIBLE
            else State.UNKNOWN,
            reason,
        )

    if member.state is MembershipState.CONFLICTED:
        return result(State.CONFLICTED, Reason.CONFLICT)
    if member.state is MembershipState.EXCLUDED:
        return result(State.INELIGIBLE, Reason.NOT_MEMBER)
    if member.state is not MembershipState.INCLUDED:
        return missing(Reason.UNKNOWN_MEMBERSHIP)
    records = active_records(
        repository, record_candidates(repository, SecurityRecord, build_id, security), at, known
    )
    if len(records) != 1:
        return missing()
    master = records[0]
    refs.append(master.fingerprint)
    issuers = active_records(
        repository,
        record_candidates(repository, IssuerRecord, build_id, issuer=master.issuer),
        at,
        known,
    )
    issuer = next((item for item in issuers if item.issuer == master.issuer), None)
    if issuer is None:
        return missing()
    refs.append(issuer.fingerprint)
    if master.security_type not in policy.security_types:
        return result(State.INELIGIBLE, Reason.WRONG_SECURITY_TYPE)
    if policy.countries and master.country not in policy.countries:
        return result(State.INELIGIBLE, Reason.WRONG_COUNTRY)
    events = active_records(
        repository, record_candidates(repository, LifecycleEvent, build_id, security), at, known
    )
    refs.extend(value.fingerprint for value in events)
    terminals = tuple(
        value
        for value in events
        if value.kind in (LifecycleKind.DELISTING, LifecycleKind.RELISTING)
    )
    if terminals:
        latest = max(value.evidence.validity.start_ns for value in terminals)
        kinds = {
            value.kind for value in terminals if value.evidence.validity.start_ns == latest
        }
        if len(kinds) > 1:
            return result(State.CONFLICTED, Reason.CONFLICT)
        if LifecycleKind.DELISTING in kinds:
            return result(State.INELIGIBLE, Reason.DELISTED)
    listing_values = active_records(
        repository, record_candidates(repository, ListingRecord, build_id, security), at, known
    )
    choices = tuple(
        value
        for value in listing_values
        if (not policy.primary_only or value.primary)
        and (policy.selected_listing is None or value.listing == policy.selected_listing)
    )
    if not choices:
        future = record_candidates(repository, ListingRecord, build_id, security)
        if any(
            value.evidence.known(known) and value.evidence.validity.start_ns > at
            for value in future
        ):
            return result(State.NOT_AVAILABLE_YET, Reason.NOT_YET_LISTED)
        return missing()
    if len(choices) != 1:
        return result(State.CONFLICTED, Reason.CONFLICT)
    listing = choices[0]
    refs.append(listing.fingerprint)
    if policy.venues and listing.venue not in policy.venues:
        return result(State.INELIGIBLE, Reason.WRONG_VENUE)
    if (policy.currencies and listing.currency not in policy.currencies) or (
        policy.price_currency is not None and listing.currency != policy.price_currency
    ):
        return result(State.NOT_APPLICABLE, Reason.CURRENCY_MISMATCH)
    calendars = active_records(
        repository, record_candidates(repository, UniverseCalendar, build_id), at, known
    )
    calendar = next(
        (value for value in calendars if value.fingerprint == definition.calendar.fingerprint),
        None,
    )
    if calendar is None:
        return missing()
    if listing.calendar_id != calendar.calendar_id or listing.venue != calendar.venue:
        return result(State.NOT_APPLICABLE, Reason.WRONG_VENUE)
    refs.append(calendar.fingerprint)
    eligible_sessions = tuple(
        value for value in calendar.sessions if policy.include_extended or not value.extended
    )
    if policy.require_active_session and not any(
        value.period.contains(at) for value in eligible_sessions
    ):
        return result(State.INELIGIBLE, Reason.MARKET_CLOSED)
    sessions = sum(
        listing.evidence.validity.start_ns <= value.period.start_ns
        and value.period.end_ns <= min(at, known)
        for value in eligible_sessions
    )
    if sessions < policy.minimum_listing_sessions:
        return result(State.INELIGIBLE, Reason.INSUFFICIENT_LISTING_AGE)
    for cls in (SymbolAssignment, SecurityRelationship, ExternalIdentifier):
        refs.extend(
            value.fingerprint
            for value in active_records(
                repository, record_candidates(repository, cls, build_id, security), at, known
            )
        )
    identifiers = active_records(
        repository,
        record_candidates(repository, ExternalIdentifier, build_id, security),
        at,
        known,
    )
    authoritative: dict[tuple[object, str], set[str]] = {}
    for identifier in identifiers:
        authoritative.setdefault((identifier.kind, identifier.authority), set()).add(
            identifier.value
        )
        owner = identifier.kind.value + "|" + identifier.authority + "|" + identifier.value
        assignments = active_records(
            repository,
            record_candidates(repository, ExternalIdentifier, build_id, owner=owner),
            at,
            known,
        )
        refs.extend(value.fingerprint for value in assignments)
        if len({value.security for value in assignments}) > 1:
            return result(State.CONFLICTED, Reason.CONFLICT)
    if any(len(values) > 1 for values in authoritative.values()):
        return result(State.CONFLICTED, Reason.CONFLICT)
    if policy.require_tradable:
        states = precedence(
            active_records(
                repository,
                record_candidates(
                    repository, TradabilityRecord, build_id, security, listing=listing.listing
                ),
                at,
                known,
            )
        )
        refs.extend(value.fingerprint for value in states)
        known_states = {value.state for value in states}
        if len(known_states) > 1:
            return result(State.CONFLICTED, Reason.CONFLICT)
        if not known_states or TradabilityState.UNKNOWN in known_states:
            return missing()
        current = next(iter(known_states))
        if current is not TradabilityState.TRADABLE:
            reason = {
                TradabilityState.HALTED: Reason.HALTED,
                TradabilityState.SUSPENDED: Reason.SUSPENDED,
                TradabilityState.DELISTED: Reason.DELISTED,
            }[current]
            return result(State.INELIGIBLE, reason)
    try:
        prices = (
            observations(repository, build_id, policy.price_feature, security, at)
            if policy.price_feature
            else ()
        )
        volumes = (
            observations(
                repository,
                build_id,
                policy.volume_feature,
                security,
                at,
                max(0, at - policy.lookback_ns + 1),
            )
            if policy.volume_feature
            else ()
        )
    except ContractError as error:
        from afre.feature_store.queries import VintageConflict

        if isinstance(error, VintageConflict):
            return result(State.CONFLICTED, Reason.CONFLICT)
        raise
    market.extend(value.fingerprint for value in (*prices, *volumes))
    if policy.price_feature is not None:
        if not prices or not usable(prices[-1], at) or cast(float, prices[-1].value) <= 0:
            return missing(
                Reason.STALE_MARKET_DATA
                if prices
                and prices[-1].feature.freshness.stale(
                    at, prices[-1].effective_ns, prices[-1].clocks.final_available_ns
                )
                else Reason.MISSING_DATA
            )
        price = float(cast(float, prices[-1].value))
        if policy.minimum_price is not None and price < policy.minimum_price:
            return result(State.INELIGIBLE, Reason.PRICE_TOO_LOW)
    history = {
        value.effective_ns: float(cast(float, value.value))
        for value in prices
        if value.effective_ns > at - policy.lookback_ns
        and usable(value, at)
        and cast(float, value.value) > 0
    }
    count = len(history)
    if count < policy.minimum_data_observations:
        return result(State.INELIGIBLE, Reason.INSUFFICIENT_HISTORY)
    if policy.volume_feature is not None:
        if len(volumes) < policy.minimum_liquidity_observations or any(
            not usable(value, at) or cast(float, value.value) < 0 for value in volumes
        ):
            return missing()
        volume = math.fsum(float(cast(float, value.value)) for value in volumes)
        if policy.minimum_share_volume is not None and volume < policy.minimum_share_volume:
            return result(State.INELIGIBLE, Reason.INSUFFICIENT_VOLUME)
        if policy.minimum_mean_dollar_volume is not None:
            if any(value.effective_ns not in history for value in volumes):
                return missing()
            dollar = math.fsum(
                history[value.effective_ns] * float(cast(float, value.value))
                for value in volumes
            ) / len(volumes)
            if dollar < policy.minimum_mean_dollar_volume:
                return result(State.INELIGIBLE, Reason.INSUFFICIENT_LIQUIDITY)
    return result(State.ELIGIBLE, Reason.PASSED)
