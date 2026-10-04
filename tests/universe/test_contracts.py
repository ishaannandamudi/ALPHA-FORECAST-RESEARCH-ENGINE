from dataclasses import replace
from typing import Any

import pytest

from afre.feature_store import AvailabilityEvidence
from afre.feature_store.schema import StoreScope, ValidityRule
from afre.schema import ContractError
from afre.serialization import canonical_json, deserialize
from afre.time import TimeRange
from afre.universe import (
    IssuerRecord,
    ListingId,
    SecurityRecord,
    SecurityRelationship,
    StableIssuerId,
    StableSecurityId,
    UniverseBounds,
    UniverseSession,
)
from afre.universe.models import SecurityResolution
from afre.universe.repository import evidence_of
from afre.universe.schema import (
    EligibilityReason,
    EligibilityState,
    RelationshipKind,
    SecurityType,
)
from examples.feature_store_demo import SOURCE
from examples.universe_demo import ISSUERS, LISTINGS, SECURITIES, DemoFixture, evidence
from tests.universe.test_queries import insert


def test_contract_roundtrip_typed_security_issuer_and_listing(fixture: DemoFixture) -> None:
    values = (
        fixture.universe,
        fixture.snapshot,
        fixture.universe.eligibility,
        SECURITIES[0],
        ISSUERS[0],
        LISTINGS[0],
        *fixture.engine.security_history(SECURITIES[0], 30),
    )
    for value in values:
        assert deserialize(canonical_json(value)) == value
    with pytest.raises(ContractError):
        StableSecurityId("ticker namespace", "OLD")
    with pytest.raises(ContractError):
        StableIssuerId("issuer", " ")
    with pytest.raises(ContractError):
        ListingId("listing", "control\n")
    with pytest.raises(ContractError):
        IssuerRecord(ISSUERS[0], "US", evidence(SECURITIES[0].instrument))
    master = fixture.engine.repository.master(
        SecurityRecord, SECURITIES[0].instrument.fingerprint
    )
    with pytest.raises(ContractError):
        replace(master, issuer=StableIssuerId(SECURITIES[0].namespace, SECURITIES[0].value))
    with pytest.raises(ContractError):
        replace(master, evidence=replace(master.evidence, predecessor_id=master.fingerprint))
    with pytest.raises(ContractError):
        replace(master.evidence, knowledge_until_ns=0)
    with pytest.raises(ContractError):
        replace(master.evidence, predecessor_id=SOURCE.fingerprint)
    with pytest.raises(ContractError):
        evidence_of(fixture.universe)


@pytest.mark.parametrize(
    "changes",
    [
        {"security_types": ()},
        {"security_types": ("common",)},
        {"security_types": (SecurityType.COMMON_STOCK, SecurityType.COMMON_STOCK)},
        {"venues": ("X", "X")},
        {"minimum_listing_sessions": -1},
        {"minimum_data_observations": -1},
        {"lookback_ns": 0},
        {"minimum_liquidity_observations": 0},
        {"minimum_price": -1.0},
        {"price_feature": None},
        {"price_currency": "EUR"},
        {"volume_feature": None},
        {"minimum_price": float("nan")},
    ],
)
def test_invalid_policy_cannot_be_silently_normalized(
    fixture: DemoFixture, changes: dict[str, Any]
) -> None:
    with pytest.raises(ContractError):
        replace(fixture.universe.eligibility, **changes)


def test_policy_scope_unit_calendar_and_build_boundaries(fixture: DemoFixture) -> None:
    for changes in ({"scope": StoreScope.ISSUER}, {"validity_rule": ValidityRule.KNOWN_FACT}):
        with pytest.raises(ContractError):
            replace(
                fixture.universe.eligibility, price_feature=replace(fixture.price, **changes)
            )
    with pytest.raises(ContractError):
        replace(fixture.universe.eligibility, volume_feature=fixture.price)
    with pytest.raises(ContractError):
        replace(
            fixture.universe.eligibility,
            volume_feature=replace(fixture.volume, build_context="other"),
        )
    wrong = replace(fixture.price, calendar_id="other")
    with pytest.raises(ContractError, match="calendar"):
        replace(
            fixture.universe,
            eligibility=replace(
                fixture.universe.eligibility,
                price_feature=wrong,
                volume_feature=None,
                minimum_share_volume=None,
                minimum_mean_dollar_volume=None,
            ),
        )
    with pytest.raises(ContractError):
        replace(fixture.universe, name="current_ticker_filter")
    with pytest.raises(ContractError):
        replace(fixture.universe.calendar, sessions=())
    overlapping = UniverseSession("overlap", TimeRange(5, 15))
    with pytest.raises(ContractError):
        replace(
            fixture.universe.calendar,
            sessions=(*fixture.universe.calendar.sessions, overlapping),
        )
    with pytest.raises(ContractError):
        UniverseBounds(records=0)
    with pytest.raises(ContractError):
        AvailabilityEvidence(602, 602, 602, 600, 600, 600)


def test_relationship_kinds_and_foreign_references(fixture: DemoFixture) -> None:
    for kind, related, issuer, listing in (
        (RelationshipKind.SECURITY_ISSUED_BY, None, ISSUERS[0], None),
        (RelationshipKind.PRIMARY_LISTING_OF, None, None, LISTINGS[0]),
        (RelationshipKind.PREDECESSOR_OF, SECURITIES[1], None, None),
    ):
        relation = SecurityRelationship(
            SECURITIES[0], kind, related, issuer, listing, evidence(SECURITIES[0].instrument)
        )
        insert(fixture, relation)
    with pytest.raises(ContractError):
        SecurityRelationship(
            SECURITIES[0],
            RelationshipKind.SUCCESSOR_TO,
            SECURITIES[0],
            None,
            None,
            evidence(SECURITIES[0].instrument),
        )
    with pytest.raises(ContractError):
        SecurityRelationship(
            SECURITIES[0],
            RelationshipKind.SECURITY_ISSUED_BY,
            SECURITIES[1],
            None,
            None,
            evidence(SECURITIES[0].instrument),
        )
    with pytest.raises(KeyError):
        insert(
            fixture,
            SecurityRelationship(
                SECURITIES[0],
                RelationshipKind.SUCCESSOR_TO,
                StableSecurityId("synthetic-security", "missing"),
                None,
                None,
                evidence(SECURITIES[0].instrument),
            ),
        )


def test_snapshot_grid_results_audit_and_resolution_integrity(fixture: DemoFixture) -> None:
    snapshot = fixture.snapshot
    with pytest.raises(ContractError):
        replace(snapshot, eligibility=snapshot.eligibility[:-1])
    with pytest.raises(ContractError):
        replace(snapshot, input_build_id=SOURCE.fingerprint)
    with pytest.raises(ContractError):
        replace(snapshot, builder_version="unknown")
    with pytest.raises(ContractError):
        replace(snapshot.memberships[0], record_ids=(SOURCE.fingerprint,))
    result = next(value for value in snapshot.eligibility if value.record_ids)
    with pytest.raises(ContractError):
        replace(result, state=EligibilityState.UNKNOWN, reasons=(EligibilityReason.PASSED,))
    with pytest.raises(ContractError):
        replace(result, reasons=())
    with pytest.raises(ContractError):
        replace(result, record_ids=(*result.record_ids, result.record_ids[0]))
    with pytest.raises(ContractError):
        SecurityResolution("OLD", "XTEST", 30, 30, SECURITIES[0], None, (), False)
    with pytest.raises(ContractError):
        SecurityResolution("OLD", "XTEST", 30, 30, SECURITIES[0], LISTINGS[0], (), True)
    with pytest.raises(ContractError):
        SecurityResolution("OLD", "XTEST", 30, 30, None, None, (SOURCE.fingerprint,), False)


def test_offline_provider_families_and_scope_of_identity_cache(fixture: DemoFixture) -> None:
    from afre.universe import OfflineEligibilityMarketProvider, OfflineUniverseProvider
    from afre.universe.models import UniverseInputBuild

    repository = fixture.engine.repository
    values = (
        *fixture.engine.security_history(SECURITIES[0], 70),
        repository.master(IssuerRecord, ISSUERS[0].instrument.fingerprint),
    )
    provider = OfflineUniverseProvider(values)
    assert len(provider.security_records_known_by(30)) == 2
    assert len(provider.listings_known_by(30)) == 1
    assert len(provider.symbols_known_by(30)) == 2
    assert provider.lifecycle_known_by(30) == ()
    assert len(provider.constituents_known_by(30)) == 1
    assert len(provider.tradability_known_by(30)) == 1
    from examples.feature_store_demo import source_vintage

    vintage = source_vintage(fixture.price, 5, 5)
    market = OfflineEligibilityMarketProvider((vintage,))
    assert market.market_features_known_by(4) == ()
    assert market.market_features_known_by(5) == (vintage,)
    with pytest.raises(ContractError):
        OfflineEligibilityMarketProvider((fixture.universe,))  # type: ignore[arg-type]
    build_id = fixture.snapshot.input_build_id
    with repository.read_snapshot(), repository.validation_cache():
        build = repository.resolve(UniverseInputBuild, build_id)
        assert repository.identity(build) == build_id
        assert repository.get_any(build_id) is build
        assert repository.get_any(fixture.memberships[0].fingerprint) is repository.resolve(
            type(fixture.memberships[0]), fixture.memberships[0].fingerprint
        )
    assert repository._universe_identity_cache == {}
    assert repository.identity(fixture.universe) == fixture.universe.fingerprint
