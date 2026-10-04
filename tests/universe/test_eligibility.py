from dataclasses import replace
from typing import Any

import pytest

from afre.datasets import AdjustmentBasis, AdjustmentPolicy
from afre.feature_store.freshness import FreshnessBasis, FreshnessPolicy
from afre.features import MissingState
from afre.schema import ContractError
from afre.universe import (
    ConstituentCoverage,
    ExternalIdentifier,
    LifecycleEvent,
    ListingRecord,
    TradabilityRecord,
)
from afre.universe.models import EligibilityResult
from afre.universe.schema import (
    EligibilityMissingRule,
    EligibilityReason,
    EligibilityState,
    ExternalIdentifierKind,
    LifecycleKind,
    SecurityType,
    SnapshotCompleteness,
    TradabilityState,
)
from examples.feature_store_demo import clocks, source_vintage
from examples.universe_demo import LISTINGS, SECURITIES, DemoFixture, evidence
from tests.universe.test_queries import insert


def policy_result(
    fixture: DemoFixture, at: int = 30, known: int = 30, security_index: int = 0, **changes: Any
) -> EligibilityResult:
    policy = replace(fixture.universe.eligibility, **changes)
    universe = replace(
        fixture.universe, name="universe.policy_" + policy.fingerprint[-16:], eligibility=policy
    )
    coverage = ConstituentCoverage(
        universe.fingerprint,
        SECURITIES,
        SnapshotCompleteness.COMPLETE,
        evidence(SECURITIES[0].instrument),
    )
    members = tuple(replace(m, definition_id=universe.fingerprint) for m in fixture.memberships)
    insert(fixture, universe, coverage, *members)
    snapshot = fixture.engine.universe_as_of(universe, at, known)
    return next(
        x for x in snapshot.eligibility if x.membership.security == SECURITIES[security_index]
    )


def test_exact_price_volume_dollar_history_and_future_price(fixture: DemoFixture) -> None:
    result = policy_result(fixture)
    assert result.state is EligibilityState.ELIGIBLE
    assert (result.price, result.share_volume, result.mean_dollar_volume) == (
        20.0,
        200.0,
        2000.0,
    )
    assert result.data_observations == result.completed_listing_sessions == 2
    future = source_vintage(fixture.price, 29, 31, 1.0)
    future_volume = source_vintage(fixture.volume, 29, 31, 100000.0)
    insert(fixture, future, future_volume)
    before = policy_result(fixture)
    assert before == result
    after = policy_result(fixture, at=31, known=31)
    assert after.reasons == (EligibilityReason.PRICE_TOO_LOW,)
    assert future.fingerprint in after.market_ids
    assert future.fingerprint not in before.market_ids


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"minimum_price": 21.0}, EligibilityReason.PRICE_TOO_LOW),
        ({"minimum_share_volume": 201.0}, EligibilityReason.INSUFFICIENT_VOLUME),
        ({"minimum_mean_dollar_volume": 2001.0}, EligibilityReason.INSUFFICIENT_LIQUIDITY),
        ({"minimum_data_observations": 3}, EligibilityReason.INSUFFICIENT_HISTORY),
        ({"minimum_listing_sessions": 3}, EligibilityReason.INSUFFICIENT_LISTING_AGE),
        ({"lookback_ns": 5}, EligibilityReason.INSUFFICIENT_HISTORY),
        ({"venues": ("XWRONG",)}, EligibilityReason.WRONG_VENUE),
        ({"countries": ("CA",)}, EligibilityReason.WRONG_COUNTRY),
        (
            {"security_types": (SecurityType.WARRANT, SecurityType.ETF)},
            EligibilityReason.WRONG_SECURITY_TYPE,
        ),
        ({"require_active_session": True}, EligibilityReason.MARKET_CLOSED),
        ({"currencies": ("EUR",)}, EligibilityReason.CURRENCY_MISMATCH),
    ],
)
def test_policy_failures(
    fixture: DemoFixture, changes: dict[str, Any], reason: EligibilityReason
) -> None:
    result = policy_result(fixture, **changes)
    assert result.reasons == (reason,)
    assert result.state in (EligibilityState.INELIGIBLE, EligibilityState.NOT_APPLICABLE)


def test_missing_stale_revision_conflict_and_negative_volume(fixture: DemoFixture) -> None:
    assert policy_result(fixture, at=1, known=1).state is EligibilityState.UNKNOWN
    assert (
        policy_result(
            fixture, at=1, known=1, missing_rule=EligibilityMissingRule.INELIGIBLE
        ).state
        is EligibilityState.INELIGIBLE
    )
    stale = replace(
        fixture.price,
        definition=replace(fixture.price.definition, name="market.stale_price"),
        freshness=FreshnessPolicy(FreshnessBasis.EFFECTIVE_TIME, 2),
    )
    insert(fixture, stale, source_vintage(stale, 25, 25, 20.0))
    assert policy_result(fixture, price_feature=stale).reasons == (
        EligibilityReason.STALE_MARKET_DATA,
    )
    old = source_vintage(fixture.price, 25, 25, 20.0)
    revised = replace(old, value=25.0, clocks=clocks(28), predecessor_id=old.fingerprint)
    insert(fixture, revised)
    assert policy_result(fixture).price == 25.0
    tied = replace(revised, value=26.0, predecessor_id=None)
    insert(fixture, tied)
    assert policy_result(fixture).state is EligibilityState.CONFLICTED


def test_missing_liquidity_alignment_volume_policy_and_endpoints(fixture: DemoFixture) -> None:
    # Window is (T-lookback,T]; observation at 5 is excluded at T=30/lookback=25.
    result = policy_result(fixture, lookback_ns=25, minimum_data_observations=0)
    assert result.state is EligibilityState.UNKNOWN and result.reasons == (
        EligibilityReason.MISSING_DATA,
    )
    missing = replace(
        source_vintage(fixture.volume, 25, 25, 100.0),
        value=None,
        state=MissingState.MISSING,
        clocks=clocks(28),
    )
    insert(fixture, missing)
    assert policy_result(fixture).state is EligibilityState.UNKNOWN
    negative = replace(missing, value=-1.0, state=MissingState.PRESENT, clocks=clocks(29))
    insert(fixture, negative)
    assert policy_result(fixture).state is EligibilityState.UNKNOWN


def test_dollar_volume_needs_matching_completed_price(fixture: DemoFixture) -> None:
    insert(fixture, source_vintage(fixture.volume, 15, 15, 100.0))
    assert policy_result(fixture).state is EligibilityState.UNKNOWN
    assert policy_result(fixture, minimum_mean_dollar_volume=None).share_volume == 300.0


@pytest.mark.parametrize(
    "state,reason",
    [
        (TradabilityState.HALTED, EligibilityReason.HALTED),
        (TradabilityState.SUSPENDED, EligibilityReason.SUSPENDED),
        (TradabilityState.DELISTED, EligibilityReason.DELISTED),
        (TradabilityState.UNKNOWN, EligibilityReason.MISSING_DATA),
    ],
)
def test_historical_tradability(
    fixture: DemoFixture, state: TradabilityState, reason: EligibilityReason
) -> None:
    insert(
        fixture,
        TradabilityRecord(
            LISTINGS[0], SECURITIES[0], state, evidence(SECURITIES[0].instrument, 20, 40, 28)
        ),
    )
    assert policy_result(fixture).reasons == (reason,)
    assert policy_result(fixture, require_tradable=False).state is EligibilityState.ELIGIBLE
    assert policy_result(fixture, at=25, known=25).state is EligibilityState.ELIGIBLE


def test_conflicting_tradability_and_delisting_lifecycle(fixture: DemoFixture) -> None:
    records = tuple(
        TradabilityRecord(
            LISTINGS[0], SECURITIES[0], state, evidence(SECURITIES[0].instrument, 20, 40, 28)
        )
        for state in (TradabilityState.HALTED, TradabilityState.TRADABLE)
    )
    insert(fixture, *records)
    assert policy_result(fixture).state is EligibilityState.CONFLICTED
    assert policy_result(fixture, at=70, known=70, security_index=2).reasons == (
        EligibilityReason.DELISTED,
    )
    assert policy_result(fixture, security_index=2).state is EligibilityState.ELIGIBLE
    relist = LifecycleEvent(
        SECURITIES[2],
        "relist",
        LifecycleKind.RELISTING,
        "relist",
        evidence(SECURITIES[2].instrument, 60, 1000, 55),
    )
    insert(fixture, relist)
    assert (
        policy_result(fixture, at=70, known=70, security_index=2).state
        is EligibilityState.CONFLICTED
    )


def test_identifier_conflicts_do_not_merge_securities(fixture: DemoFixture) -> None:
    first = ExternalIdentifier(
        SECURITIES[0],
        ExternalIdentifierKind.ISIN,
        "synthetic",
        "X1",
        evidence(SECURITIES[0].instrument),
    )
    second = replace(first, security=SECURITIES[1], evidence=evidence(SECURITIES[1].instrument))
    insert(fixture, first, second)
    assert policy_result(fixture).state is EligibilityState.CONFLICTED


def test_listing_currency_calendar_session_and_missing_listing(fixture: DemoFixture) -> None:
    repository = fixture.engine.repository
    original = next(
        x
        for x in fixture.engine.security_history(SECURITIES[0], 30)
        if isinstance(x, ListingRecord)
    )
    changed = replace(
        original,
        currency="EUR",
        evidence=evidence(SECURITIES[0].instrument, known=28, predecessor=original.fingerprint),
    )
    insert(fixture, changed)
    assert policy_result(fixture).state is EligibilityState.NOT_APPLICABLE
    assert policy_result(fixture, at=30, known=20, security_index=3).reasons == (
        EligibilityReason.NOT_MEMBER,
    )
    # Membership can precede the first listing; it must remain a distinct known member.
    future_listing_member = replace(
        fixture.memberships[3], evidence=evidence(SECURITIES[3].instrument, 0, 1000, 28)
    )
    insert(fixture, future_listing_member)
    snapshot = fixture.engine.universe_as_of(fixture.universe, 30, 30)
    future = next(x for x in snapshot.eligibility if x.membership.security == SECURITIES[3])
    assert future.state is EligibilityState.NOT_AVAILABLE_YET
    assert snapshot.completeness is SnapshotCompleteness.KNOWN_GAPS
    assert repository.audit() > 0


def test_explicit_extended_hours_and_session_count(fixture: DemoFixture) -> None:
    no_market: dict[str, Any] = dict(
        price_feature=None,
        price_currency=None,
        volume_feature=None,
        minimum_price=None,
        minimum_share_volume=None,
        minimum_mean_dollar_volume=None,
        minimum_data_observations=0,
    )
    assert policy_result(
        fixture, at=66, known=66, require_active_session=True, **no_market
    ).reasons == (EligibilityReason.MARKET_CLOSED,)
    result = policy_result(
        fixture,
        at=66,
        known=66,
        require_active_session=True,
        include_extended=True,
        **no_market,
    )
    assert result.state is EligibilityState.ELIGIBLE and result.completed_listing_sessions == 4
    assert (
        policy_result(fixture, at=25, known=25, require_active_session=True).state
        is EligibilityState.ELIGIBLE
    )


def test_future_adjustment_cannot_enter_eligibility(fixture: DemoFixture) -> None:
    feature = replace(
        fixture.price,
        definition=replace(fixture.price.definition, name="market.future_adjustment"),
        adjustment=AdjustmentPolicy(AdjustmentBasis.RAW, 31),
    )
    insert(fixture, feature)
    with pytest.raises(ContractError, match="future feature adjustment"):
        policy_result(
            fixture,
            price_feature=feature,
            volume_feature=None,
            minimum_share_volume=None,
            minimum_mean_dollar_volume=None,
        )


@pytest.mark.parametrize(
    "security_type", [kind for kind in SecurityType if kind is not SecurityType.COMMON_STOCK]
)
def test_common_stock_filter_rejects_distinct_security_types(
    fixture: DemoFixture, security_type: SecurityType
) -> None:
    from afre.universe import SecurityRecord, StableSecurityId, UniverseMembershipVintage
    from afre.universe.schema import MembershipState
    from examples.universe_demo import ISSUERS

    security = StableSecurityId("synthetic-security", security_type.value)
    master = SecurityRecord(
        security,
        ISSUERS[0],
        security_type,
        "B",
        "equity",
        "USD",
        "US",
        evidence(security.instrument),
    )
    member = UniverseMembershipVintage(
        fixture.universe.fingerprint,
        security,
        MembershipState.INCLUDED,
        evidence(security.instrument),
    )
    insert(fixture, master, member)
    snapshot = fixture.engine.universe_as_of(fixture.universe, 30, 30)
    result = next(
        value for value in snapshot.eligibility if value.membership.security == security
    )
    assert result.reasons == (EligibilityReason.WRONG_SECURITY_TYPE,)
    assert master.issuer == ISSUERS[0] and security != SECURITIES[0]


def test_explicit_secondary_listing_and_missing_listing_calendar(fixture: DemoFixture) -> None:
    from afre.universe import ListingId

    secondary = ListingId("synthetic-listing", "secondary")
    listing = ListingRecord(
        secondary,
        SECURITIES[0],
        "XTEST",
        "USD",
        False,
        fixture.universe.calendar.calendar_id,
        evidence(SECURITIES[0].instrument),
    )
    tradability = TradabilityRecord(
        secondary, SECURITIES[0], TradabilityState.TRADABLE, evidence(SECURITIES[0].instrument)
    )
    insert(fixture, listing, tradability)
    assert policy_result(fixture, primary_only=False).state is EligibilityState.CONFLICTED
    selected = policy_result(fixture, primary_only=False, selected_listing=secondary)
    assert selected.state is EligibilityState.ELIGIBLE and selected.listing == secondary
    wrong = replace(
        listing,
        calendar_id="wrong",
        evidence=evidence(SECURITIES[0].instrument, known=28, predecessor=listing.fingerprint),
    )
    insert(fixture, wrong)
    assert (
        policy_result(fixture, primary_only=False, selected_listing=secondary).state
        is EligibilityState.NOT_APPLICABLE
    )


def test_merger_and_spinoff_preserve_original_market_and_membership(
    fixture: DemoFixture,
) -> None:
    from afre.universe import SecurityRelationship
    from afre.universe.schema import RelationshipKind

    for security, kind, related in (
        (SECURITIES[2], LifecycleKind.MERGER, SECURITIES[0]),
        (SECURITIES[1], LifecycleKind.SPINOFF, SECURITIES[0]),
    ):
        insert(
            fixture,
            LifecycleEvent(
                security,
                "event-" + kind.value,
                kind,
                "supplied event",
                evidence(security.instrument, 20, 1000, 20),
            ),
            SecurityRelationship(
                security,
                RelationshipKind.SUCCESSOR_TO
                if kind is LifecycleKind.MERGER
                else RelationshipKind.SPINOFF_FROM,
                related,
                None,
                None,
                evidence(security.instrument, 20, 1000, 20),
            ),
        )
    for index in (1, 2):
        result = policy_result(fixture, security_index=index)
        assert result.state is EligibilityState.ELIGIBLE
        assert result.membership.security == SECURITIES[index]
        assert result.price == 20.0 + index
