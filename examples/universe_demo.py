"""Offline AFRE-3: identities, historical membership, eligibility and frozen replay."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.feature_store import AvailabilityEvidence, RegisteredFeatureDefinition
from afre.ids import InstrumentId
from afre.serialization import canonical_json
from afre.time import TimeRange
from afre.universe import (
    ConstituentCoverage,
    EligibilityPolicy,
    IssuerRecord,
    LifecycleEvent,
    ListingId,
    ListingRecord,
    SecurityRecord,
    StableIssuerId,
    StableSecurityId,
    SymbolAssignment,
    TradabilityRecord,
    UniverseCalendar,
    UniverseDefinition,
    UniverseEngine,
    UniverseEvidence,
    UniverseMembershipVintage,
    UniverseRepository,
    UniverseSession,
    UniverseSnapshot,
)
from afre.universe.schema import (
    EligibilityState,
    LifecycleKind,
    MembershipState,
    SecurityType,
    SnapshotCompleteness,
    TradabilityState,
    UniverseSourceKind,
)
from examples.feature_store_demo import CALENDAR, SOURCE, clocks, definition, source_vintage

SECURITIES = tuple(
    StableSecurityId("synthetic-security", f"{index:04d}") for index in range(1, 5)
)
ISSUERS = tuple(StableIssuerId("synthetic-issuer", f"{index:04d}") for index in range(1, 5))
LISTINGS = tuple(ListingId("synthetic-listing", f"{index:04d}") for index in range(1, 5))


def evidence(
    entity: InstrumentId,
    start: int = 0,
    end: int = 1000,
    known: int = 0,
    predecessor: str | None = None,
    availability: AvailabilityEvidence | None = None,
) -> UniverseEvidence:
    return UniverseEvidence(
        TimeRange(start, end),
        entity,
        SOURCE,
        availability or clocks(known),
        predecessor_id=predecessor,
    )


def calendar() -> UniverseCalendar:
    return UniverseCalendar(
        CALENDAR,
        "1",
        "XTEST",
        "UTC",
        tuple(
            UniverseSession(f"session-{start}", TimeRange(start, end), extended)
            for start, end, extended in (
                (0, 10, False),
                (20, 30, False),
                (40, 50, False),
                (60, 65, False),
                (65, 70, True),
            )
        ),
        evidence(InstrumentId("calendar", "synthetic")),
    )


@dataclass(frozen=True)
class DemoFixture:
    engine: UniverseEngine
    universe: UniverseDefinition
    price: RegisteredFeatureDefinition
    volume: RegisteredFeatureDefinition
    memberships: tuple[UniverseMembershipVintage, ...]
    snapshot: UniverseSnapshot


def populate(repository: UniverseRepository, reverse: bool = False) -> DemoFixture:
    price = definition("market.eligibility_price", "USD")
    volume = definition("market.eligibility_volume", "shares")
    universe = UniverseDefinition(
        "universe.synthetic",
        "1",
        UniverseSourceKind.INDEX_MEMBERSHIP,
        SOURCE,
        EligibilityPolicy(
            price_feature=price,
            volume_feature=volume,
            price_currency="USD",
            minimum_price=10.0,
            minimum_share_volume=100.0,
            minimum_mean_dollar_volume=1000.0,
            lookback_ns=30,
            minimum_data_observations=2,
            minimum_liquidity_observations=2,
        ),
        calendar(),
    )
    order = tuple(reversed(range(4))) if reverse else tuple(range(4))
    with repository.transaction(), repository.validation_cache():
        repository.put(SOURCE)
        repository.put(price)
        repository.put(volume)
        repository.put(universe.calendar)
        for index in order:
            repository.put(
                IssuerRecord(ISSUERS[index], "US", evidence(ISSUERS[index].instrument))
            )
            repository.put(
                SecurityRecord(
                    SECURITIES[index],
                    ISSUERS[index],
                    SecurityType.COMMON_STOCK,
                    "A",
                    "equity",
                    "USD",
                    "US",
                    evidence(SECURITIES[index].instrument),
                )
            )
            start, end = (60, 1000) if index == 3 else (0, 60 if index == 2 else 1000)
            repository.put(
                ListingRecord(
                    LISTINGS[index],
                    SECURITIES[index],
                    "XTEST",
                    "USD",
                    True,
                    CALENDAR,
                    evidence(SECURITIES[index].instrument, start, end),
                )
            )
            repository.put(
                TradabilityRecord(
                    LISTINGS[index],
                    SECURITIES[index],
                    TradabilityState.TRADABLE,
                    evidence(SECURITIES[index].instrument, start, end),
                )
            )
        for index in order:
            assignments = (
                (("OLD", 0, 40), ("NEW", 40, 1000))
                if index == 0
                else (
                    (("ABC", 0, 60),)
                    if index == 2
                    else ((("ABC", 60, 1000),) if index == 3 else (("BBB", 0, 1000),))
                )
            )
            for symbol, start, end in assignments:
                repository.put(
                    SymbolAssignment(
                        LISTINGS[index],
                        SECURITIES[index],
                        symbol,
                        "XTEST",
                        evidence(SECURITIES[index].instrument, start, end),
                    )
                )
        repository.put(universe)
        repository.put(
            ConstituentCoverage(
                universe.fingerprint,
                SECURITIES,
                SnapshotCompleteness.COMPLETE,
                evidence(InstrumentId("universe", "demo")),
            )
        )
        members = tuple(
            UniverseMembershipVintage(
                universe.fingerprint,
                SECURITIES[index],
                MembershipState.INCLUDED,
                evidence(
                    SECURITIES[index].instrument,
                    60 if index == 3 else 0,
                    1000,
                    20 if index == 3 else 0,
                ),
            )
            for index in range(4)
        )
        for index in order:
            repository.put(members[index])
            for at in (5, 25):
                repository.put(
                    source_vintage(
                        price, at, at, 20.0 + index, entity=SECURITIES[index].instrument
                    )
                )
                repository.put(
                    source_vintage(volume, at, at, 100.0, entity=SECURITIES[index].instrument)
                )
        repository.put(
            LifecycleEvent(
                SECURITIES[2],
                "delist-c",
                LifecycleKind.DELISTING,
                "Synthetic delisting",
                evidence(SECURITIES[2].instrument, 60, 1000, 55),
            )
        )
    engine = UniverseEngine(repository)
    snapshot = engine.universe_as_of(universe, 30, 30)
    engine.persist_snapshot(snapshot)
    return DemoFixture(engine, universe, price, volume, members, snapshot)


def correction(fixture: DemoFixture) -> UniverseMembershipVintage:
    old = fixture.memberships[2]
    return replace(
        old,
        state=MembershipState.EXCLUDED,
        evidence=evidence(old.security.instrument, known=80, predecessor=old.fingerprint),
    )


def main() -> None:
    with TemporaryDirectory(prefix="afre-universe-") as directory:
        path = Path(directory) / "universe.sqlite"
        with UniverseRepository(path) as repository:
            fixture = populate(repository)
            engine = fixture.engine
            before = canonical_json(fixture.snapshot)
            assert engine.resolve_security("OLD", "XTEST", 30, 30).security == SECURITIES[0]
            assert engine.resolve_security("NEW", "XTEST", 50, 50).security == SECURITIES[0]
            assert engine.resolve_security("ABC", "XTEST", 30, 30).security == SECURITIES[2]
            assert engine.resolve_security("ABC", "XTEST", 70, 70).security == SECURITIES[3]
            future = engine.membership_as_of(fixture.universe, SECURITIES[3], 30, 30)
            assert future.state is MembershipState.EXCLUDED and future.future_record_ids
            later = engine.universe_as_of(fixture.universe, 70, 70)
            dead = next(x for x in later.eligibility if x.membership.security == SECURITIES[2])
            assert dead.state is EligibilityState.INELIGIBLE
            with repository.transaction():
                repository.put(correction(fixture))
            corrected = engine.universe_as_of(fixture.universe, 30, 80)
            engine.persist_snapshot(corrected)
            assert corrected.fingerprint != fixture.snapshot.fingerprint
            assert (
                canonical_json(repository.get(UniverseSnapshot, fixture.snapshot.fingerprint))
                == before
            )
            audit = engine.audit_security(fixture.snapshot.fingerprint, SECURITIES[2])
            with repository.transaction():
                repository.put(audit)
            count = engine.audit()
        with UniverseRepository(path) as restarted:
            saved = restarted.get(UniverseSnapshot, fixture.snapshot.fingerprint)
            replay = UniverseEngine(restarted).universe_as_of(
                saved.definition, 30, 30, saved.input_build_id
            )
            assert canonical_json(saved) == canonical_json(replay) == before
        print(
            "Historical delisted member retained; future inclusion excluded; "
            "ticker reuse distinct"
        )
        print(
            "Later membership correction creates a new snapshot; byte-identical restart replay"
        )
        print(
            f"Eligibility audit: {len(audit.lineage_ids)} evidence nodes; "
            f"{count} artifacts audited"
        )
        print(f"Snapshot: {fixture.snapshot.fingerprint}")


if __name__ == "__main__":
    main()
