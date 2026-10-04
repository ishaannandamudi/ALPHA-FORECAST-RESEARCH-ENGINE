import os
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from afre.feature_store import AvailabilityEvidence, QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind, QueryPolicy
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.universe import (
    ConstituentCoverage,
    ListingId,
    ListingRecord,
    OfflineUniverseProvider,
    SecurityRelationship,
    StableSecurityId,
    SymbolAssignment,
    UniverseEngine,
    UniverseMembershipVintage,
    UniverseRepository,
    UniverseSnapshot,
)
from afre.universe.schema import (
    MembershipState,
    RelationshipKind,
    SnapshotCompleteness,
    UniverseSourceKind,
)
from examples.feature_store_demo import SOURCE
from examples.universe_demo import (
    SECURITIES,
    DemoFixture,
    correction,
    evidence,
    populate,
)


def insert(fixture: DemoFixture, *records: Any) -> None:
    with fixture.engine.repository.transaction():
        for record in records:
            fixture.engine.repository.put(record)


def test_historical_survivorship_future_announcement_and_boundaries(
    fixture: DemoFixture,
) -> None:
    engine, universe = fixture.engine, fixture.universe
    assert (
        engine.membership_as_of(universe, SECURITIES[2], 30, 90).state
        is MembershipState.INCLUDED
    )
    future = engine.membership_as_of(universe, SECURITIES[3], 59, 30)
    assert future.state is MembershipState.EXCLUDED and future.future_record_ids
    assert (
        engine.membership_as_of(universe, SECURITIES[3], 60, 30).state
        is MembershipState.INCLUDED
    )
    assert (
        engine.membership_as_of(universe, SECURITIES[0], 1000, 30).state
        is MembershipState.UNKNOWN
    )
    assert len(engine.universe_history(universe, 30)) == 4
    assert len(engine.security_history(SECURITIES[0], 30)) >= 5
    assert engine.snapshot_history(universe, 30) == (fixture.snapshot,)


def test_symbol_change_reuse_venue_and_dual_listing(fixture: DemoFixture) -> None:
    engine = fixture.engine
    for symbol_text, at, expected in (
        ("OLD", 39, SECURITIES[0]),
        ("NEW", 40, SECURITIES[0]),
        ("ABC", 59, SECURITIES[2]),
        ("ABC", 60, SECURITIES[3]),
    ):
        assert engine.resolve_security(symbol_text, "XTEST", at, 30).security == expected
    assert engine.resolve_security("OLD", "XOTHER", 30, 30).security is None
    assert engine.resolve_security("OLD", "XTEST", 40, 30).security is None
    other = ListingId("synthetic-listing", "dual")
    listing = ListingRecord(
        other,
        SECURITIES[0],
        "XOTHER",
        "USD",
        False,
        fixture.universe.calendar.calendar_id,
        evidence(SECURITIES[0].instrument),
    )
    symbol = SymbolAssignment(
        other, SECURITIES[0], "OLD", "XOTHER", evidence(SECURITIES[0].instrument)
    )
    insert(fixture, listing, symbol)
    assert engine.resolve_security("OLD", "XOTHER", 30, 30).listing == other
    moved = replace(listing, venue="XMOVED", evidence=evidence(SECURITIES[0].instrument, 40))
    changed = replace(
        symbol, symbol="MOVED", venue="XMOVED", evidence=evidence(SECURITIES[0].instrument, 40)
    )
    insert(fixture, moved, changed)
    assert engine.resolve_security("MOVED", "XMOVED", 40, 30).listing == other
    # Equal symbols on two admissible listings are explicit ambiguity.
    ambiguous = replace(
        symbol, venue="XTEST", evidence=evidence(SECURITIES[0].instrument, 0, 40)
    )
    alternate = replace(listing, venue="XTEST")
    insert(fixture, alternate, ambiguous)
    assert engine.resolve_security("OLD", "XTEST", 30, 30).conflicted


def test_revisions_frozen_restart_and_corrected_identity(
    fixture: DemoFixture, tmp_path: Path
) -> None:
    before = canonical_json(fixture.snapshot)
    insert(fixture, correction(fixture))
    old = fixture.engine.universe_as_of(
        fixture.universe, 30, 30, fixture.snapshot.input_build_id
    )
    assert canonical_json(old) == before
    assert (
        fixture.engine.membership_as_of(fixture.universe, SECURITIES[2], 30, 30).state
        is MembershipState.INCLUDED
    )
    fresh = fixture.engine.universe_as_of(fixture.universe, 30, 80)
    fixture.engine.persist_snapshot(fresh)
    assert fresh.fingerprint != old.fingerprint
    assert (
        next(m for m in fresh.memberships if m.security == SECURITIES[2]).state
        is MembershipState.EXCLUDED
    )
    with UniverseRepository(tmp_path / "universe.sqlite") as restart:
        saved = restart.get(UniverseSnapshot, old.fingerprint)
        assert canonical_json(saved) == before
        assert restart.audit() > 0


def test_membership_conflict_unknown_complete_and_rule_sources(fixture: DemoFixture) -> None:
    old = fixture.memberships[0]
    insert(fixture, replace(old, state=MembershipState.EXCLUDED))
    assert (
        fixture.engine.membership_as_of(fixture.universe, SECURITIES[0], 30, 30).state
        is MembershipState.CONFLICTED
    )
    for index, kind in enumerate(
        (
            UniverseSourceKind.RULE_BASED,
            UniverseSourceKind.EXCHANGE_LISTING_SET,
            UniverseSourceKind.ETF_CONSTITUENT,
            UniverseSourceKind.SUPPLIED_MEMBERSHIP,
        )
    ):
        definition = replace(
            fixture.universe, name=f"universe.source_{index}", source_kind=kind
        )
        coverage = ConstituentCoverage(
            definition.fingerprint,
            SECURITIES,
            SnapshotCompleteness.KNOWN_GAPS,
            evidence(SECURITIES[0].instrument),
        )
        insert(fixture, definition, coverage)
        selected = fixture.engine.membership_as_of(definition, SECURITIES[0], 30, 30)
        expected = MembershipState.INCLUDED if index < 2 else MembershipState.UNKNOWN
        assert selected.state is expected
        assert (
            fixture.engine.universe_as_of(definition, 30, 30).completeness
            is SnapshotCompleteness.KNOWN_GAPS
        )
    bare = replace(fixture.universe, name="universe.no_coverage")
    insert(fixture, bare)
    assert (
        fixture.engine.universe_as_of(bare, 30, 30).completeness is SnapshotCompleteness.UNKNOWN
    )
    duplicate = ConstituentCoverage(
        fixture.universe.fingerprint,
        SECURITIES[:2],
        SnapshotCompleteness.COMPLETE,
        evidence(SECURITIES[0].instrument),
    )
    insert(fixture, duplicate)
    assert (
        fixture.engine.membership_as_of(fixture.universe, SECURITIES[1], 30, 30).state
        is MembershipState.CONFLICTED
    )


def test_late_unqualified_and_qualified_reconstruction(fixture: DemoFixture) -> None:
    late = UniverseMembershipVintage(
        fixture.universe.fingerprint,
        SECURITIES[3],
        MembershipState.INCLUDED,
        evidence(
            SECURITIES[3].instrument,
            0,
            20,
            availability=AvailabilityEvidence(
                1000, 1001, 1002, 1002, 10, 10, AvailabilityMode.RECONSTRUCTED
            ),
        ),
    )
    insert(fixture, late)
    assert (
        fixture.engine.membership_as_of(fixture.universe, SECURITIES[3], 15, 15).state
        is MembershipState.EXCLUDED
    )
    assert (
        fixture.engine.membership_as_of(fixture.universe, SECURITIES[3], 15, 1002).state
        is MembershipState.INCLUDED
    )
    proof = QualifiedHistoricalDelivery(
        SOURCE.fingerprint,
        SECURITIES[3].instrument,
        DeliveryEvidenceKind.AFRE_DELIVERY_LOG,
        10,
        11,
        12,
        1001,
        "approved-archive",
        "delivery-log",
        "1",
        SOURCE.provenance,
    )
    qualified = replace(
        late,
        evidence=evidence(
            SECURITIES[3].instrument,
            0,
            20,
            availability=AvailabilityEvidence(
                1000, 1001, 1002, 12, 10, 10, AvailabilityMode.RECONSTRUCTED, proof
            ),
        ),
    )
    insert(fixture, qualified)
    with pytest.raises(ContractError, match="locally approved"):
        fixture.engine.membership_as_of(
            fixture.universe, SECURITIES[3], 15, 15, constructed_ns=1002
        )
    approved = UniverseEngine(
        fixture.engine.repository,
        QueryPolicy(approved_delivery_attestors=("approved-archive",)),
    )
    selected = approved.membership_as_of(
        fixture.universe, SECURITIES[3], 15, 15, constructed_ns=1002
    )
    assert selected.state is MembershipState.INCLUDED
    assert qualified.evidence.clocks.afre_received_ns == 1000
    with pytest.raises(ContractError, match="backdated/future"):
        approved.freeze_source(15)


def test_live_publication_is_not_receipt_and_lifecycle_relationships(
    fixture: DemoFixture,
) -> None:
    delayed = replace(
        fixture.memberships[3],
        evidence=evidence(
            SECURITIES[3].instrument,
            0,
            1000,
            availability=AvailabilityEvidence(602, 602, 602, 602, 600, 600),
        ),
    )
    insert(fixture, delayed)
    assert (
        fixture.engine.membership_as_of(fixture.universe, SECURITIES[3], 10, 601).state
        is MembershipState.EXCLUDED
    )
    assert (
        fixture.engine.membership_as_of(fixture.universe, SECURITIES[3], 10, 602).state
        is MembershipState.INCLUDED
    )
    for kind in (
        RelationshipKind.SUCCESSOR_TO,
        RelationshipKind.SPINOFF_FROM,
        RelationshipKind.ADR_OF,
    ):
        insert(
            fixture,
            SecurityRelationship(
                SECURITIES[1],
                kind,
                SECURITIES[0],
                None,
                None,
                evidence(SECURITIES[1].instrument),
            ),
        )
    assert SECURITIES[0] != SECURITIES[1]
    assert len(fixture.engine.security_history(SECURITIES[1], 30)) >= 7


def test_ticker_join_is_forbidden_and_provider_deterministic(fixture: DemoFixture) -> None:
    with pytest.raises(ContractError, match="symbol-only"):
        fixture.engine.membership_as_of(fixture.universe, "OLD", 30, 30)  # type: ignore[arg-type]
    provider = OfflineUniverseProvider(tuple(reversed(fixture.memberships)))
    assert provider.records_known_by(0) == tuple(
        sorted(fixture.memberships[:3], key=lambda x: x.fingerprint)
    )
    with pytest.raises(ContractError):
        OfflineUniverseProvider((fixture.universe,))
    with pytest.raises(ContractError):
        replace(fixture.universe, source_kind=UniverseSourceKind.CURRENT_CONSTITUENTS)
    assert StableSecurityId("synthetic-security", "0001").instrument == SECURITIES[0].instrument


def test_reverse_insertion_and_hash_seeds(tmp_path: Path) -> None:
    with (
        UniverseRepository(tmp_path / "first.sqlite") as first,
        UniverseRepository(tmp_path / "reverse.sqlite") as reverse,
    ):
        forward = populate(first).snapshot
        backward = populate(reverse, reverse=True).snapshot
        assert canonical_json(forward) == canonical_json(backward)
    code = """import socket, tempfile
from pathlib import Path
from afre.universe import UniverseRepository
from afre.serialization import canonical_json
from examples.universe_demo import populate
def denied(*a, **k): raise AssertionError("network forbidden")
for name in ("socket","create_connection","getaddrinfo","gethostbyname",
             "gethostbyname_ex","gethostbyaddr","socketpair"):
    setattr(socket, name, denied)
with tempfile.TemporaryDirectory() as directory:
    with UniverseRepository(Path(directory)/"universe.sqlite") as repository:
        print(canonical_json(populate(repository).snapshot))
"""
    for seed in ("0", "1", "42", "random"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH="src:.")
        completed = subprocess.run(
            [sys.executable, "-c", code], env=env, check=True, capture_output=True, text=True
        )
        assert completed.stdout.rstrip() == canonical_json(forward)
    with pytest.raises(AssertionError):
        socket.getaddrinfo("offline.invalid", 443)


def test_revised_interval_supersedes_old_and_unknown_listing_is_not_resolved(
    fixture: DemoFixture,
) -> None:
    old = fixture.memberships[0]
    revised = replace(
        old,
        evidence=evidence(SECURITIES[0].instrument, 40, 1000, 25, predecessor=old.fingerprint),
    )
    insert(fixture, revised)
    assert (
        fixture.engine.membership_as_of(fixture.universe, SECURITIES[0], 30, 24).state
        is MembershipState.INCLUDED
    )
    selected = fixture.engine.membership_as_of(fixture.universe, SECURITIES[0], 30, 30)
    assert selected.state is MembershipState.EXCLUDED and selected.future_record_ids == (
        revised.fingerprint,
    )
    delayed_id = ListingId("synthetic-listing", "late-known")
    listing = ListingRecord(
        delayed_id,
        SECURITIES[0],
        "XLATE",
        "USD",
        False,
        fixture.universe.calendar.calendar_id,
        evidence(SECURITIES[0].instrument, 0, 1000, 20),
    )
    assignment = SymbolAssignment(
        delayed_id, SECURITIES[0], "LATE", "XLATE", evidence(SECURITIES[0].instrument)
    )
    insert(fixture, listing, assignment)
    assert fixture.engine.resolve_security("LATE", "XLATE", 10, 10).security is None
    assert fixture.engine.resolve_security("LATE", "XLATE", 10, 20).security == SECURITIES[0]
