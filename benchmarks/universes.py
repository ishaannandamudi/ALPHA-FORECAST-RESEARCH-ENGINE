"""Offline AFRE-3 profile; synthetic workload, no production latency claims."""

import cProfile
import io
import json
import pstats
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.ids import InstrumentId
from afre.serialization import canonical_json
from afre.universe import (
    ConstituentCoverage,
    EligibilityPolicy,
    IssuerRecord,
    ListingId,
    ListingRecord,
    SecurityRecord,
    StableIssuerId,
    StableSecurityId,
    SymbolAssignment,
    TradabilityRecord,
    UniverseDefinition,
    UniverseEngine,
    UniverseRepository,
    UniverseSnapshot,
)
from afre.universe.eligibility import evaluate
from afre.universe.membership import UniverseMembershipVintage
from afre.universe.schema import (
    MembershipState,
    SecurityType,
    SnapshotCompleteness,
    TradabilityState,
    UniverseSourceKind,
)
from examples.feature_store_demo import CALENDAR, SOURCE, definition, source_vintage
from examples.universe_demo import calendar, evidence


def run(securities: int = 2000) -> dict[str, object]:
    timings: dict[str, float] = {}
    price = definition("market.profile_price", "USD")
    volume = definition("market.profile_volume", "shares")
    universe = UniverseDefinition(
        "universe.profile",
        "1",
        UniverseSourceKind.INDEX_MEMBERSHIP,
        SOURCE,
        EligibilityPolicy(
            price_feature=price,
            price_currency="USD",
            volume_feature=volume,
            minimum_price=10.0,
            minimum_mean_dollar_volume=1000.0,
            minimum_listing_sessions=2,
            minimum_data_observations=2,
            minimum_liquidity_observations=2,
            lookback_ns=30,
        ),
        calendar(),
    )
    identities = tuple(
        StableSecurityId("profile-security", f"{index:06d}") for index in range(securities)
    )
    with TemporaryDirectory(prefix="afre-universe-profile-") as directory:
        path = Path(directory) / "profile.sqlite"
        start = perf_counter()
        with UniverseRepository(path) as repository:
            timings["initialize_migrate"] = perf_counter() - start
            print("Completed initialize_migrate", file=sys.stderr, flush=True)
            start = perf_counter()
            with repository.transaction(), repository.validation_cache():
                for initial in (SOURCE, price, volume, universe.calendar, universe):
                    repository.put(initial)
                for index, security in enumerate(identities):
                    issuer = StableIssuerId("profile-issuer", f"{index:06d}")
                    listing = ListingId("profile-listing", f"{index:06d}")
                    ev = evidence(security.instrument)
                    values = (
                        IssuerRecord(issuer, "US", evidence(issuer.instrument)),
                        SecurityRecord(
                            security,
                            issuer,
                            SecurityType.COMMON_STOCK,
                            "A",
                            "equity",
                            "USD",
                            "US",
                            ev,
                        ),
                        ListingRecord(listing, security, "XTEST", "USD", True, CALENDAR, ev),
                        SymbolAssignment(listing, security, f"S{index:06d}", "XTEST", ev),
                        TradabilityRecord(listing, security, TradabilityState.TRADABLE, ev),
                        UniverseMembershipVintage(
                            universe.fingerprint, security, MembershipState.INCLUDED, ev
                        ),
                    )
                    for value in values:
                        repository.put(value)
                    for at in (5, 25):
                        repository.put(
                            source_vintage(price, at, at, 20.0, entity=security.instrument)
                        )
                        repository.put(
                            source_vintage(volume, at, at, 100.0, entity=security.instrument)
                        )
                repository.put(
                    ConstituentCoverage(
                        universe.fingerprint,
                        identities,
                        SnapshotCompleteness.COMPLETE,
                        evidence(InstrumentId("universe", "profile")),
                    )
                )
            timings["ingest"] = perf_counter() - start
            print("Completed ingest", file=sys.stderr, flush=True)
            engine = UniverseEngine(repository)
            start = perf_counter()
            source = engine.freeze_source(30)
            source_id = source.fingerprint
            timings["freeze_source"] = perf_counter() - start
            print("Completed freeze_source", file=sys.stderr, flush=True)
            start = perf_counter()
            for index in range(20):
                assert (
                    engine.resolve_security(
                        f"S{index:06d}", "XTEST", 30, 30, source_id
                    ).security
                    == identities[index]
                )
            timings["20_symbol_resolutions"] = perf_counter() - start
            print("Completed 20_symbol_resolutions", file=sys.stderr, flush=True)
            start = perf_counter()
            for security in identities[:20]:
                assert (
                    engine.membership_as_of(universe, security, 30, 30, source_id).state
                    is MembershipState.INCLUDED
                )
            timings["20_membership_queries"] = perf_counter() - start
            print("Completed 20_membership_queries", file=sys.stderr, flush=True)
            profiler = cProfile.Profile()
            start = perf_counter()
            profiler.enable()
            snapshot = engine.universe_as_of(universe, 30, 30, source_id)
            profiler.disable()
            timings["snapshot_with_profile"] = perf_counter() - start
            print("Completed snapshot_with_profile", file=sys.stderr, flush=True)
            start = perf_counter()
            assert canonical_json(
                engine.universe_as_of(universe, 30, 30, source_id)
            ) == canonical_json(snapshot)
            timings["repeat_snapshot"] = perf_counter() - start
            print("Completed repeat_snapshot", file=sys.stderr, flush=True)
            start = perf_counter()
            with repository.read_snapshot(), repository.validation_cache():
                for member in snapshot.memberships[:20]:
                    evaluate(repository, universe, member)
            timings["20_eligibility_evaluations"] = perf_counter() - start
            print("Completed 20_eligibility_evaluations", file=sys.stderr, flush=True)
            start = perf_counter()
            engine.persist_snapshot(snapshot)
            timings["persist_with_replay_validation"] = perf_counter() - start
            print("Completed persist_with_replay_validation", file=sys.stderr, flush=True)
            start = perf_counter()
            audit = engine.audit_security(snapshot.fingerprint, identities[0])
            timings["security_audit_lineage"] = perf_counter() - start
            print("Completed security_audit_lineage", file=sys.stderr, flush=True)
            start = perf_counter()
            artifact_count = engine.audit()
            timings["full_integrity_audit"] = perf_counter() - start
            print("Completed full_integrity_audit", file=sys.stderr, flush=True)
            counts = {
                name: repository._connection.execute(f"SELECT count(*) FROM {name}").fetchone()[
                    0
                ]
                for name in (
                    "u_artifacts",
                    "u_records",
                    "u_build_records",
                    "u_build_features",
                    "fs_vintages",
                    "u_eligibility",
                )
            }
            plans = {}
            for name, sql, args in (
                (
                    "symbol",
                    "SELECT fingerprint FROM u_records WHERE type_name=? "
                    "AND symbol=? AND venue=? AND known_ns<=?",
                    ("SymbolAssignment", "S000000", "XTEST", 30),
                ),
                (
                    "member",
                    "SELECT fingerprint FROM u_records WHERE type_name=? "
                    "AND owner_id=? AND security_id=? AND known_ns<=?",
                    (
                        "UniverseMembershipVintage",
                        universe.fingerprint,
                        identities[0].instrument.fingerprint,
                        30,
                    ),
                ),
                (
                    "price",
                    "SELECT fingerprint FROM fs_vintages WHERE definition_id=? "
                    "AND entity_id=? AND effective_ns<=? AND available_ns<=?",
                    (price.fingerprint, identities[0].instrument.fingerprint, 30, 30),
                ),
            ):
                plans[name] = [
                    row[3]
                    for row in repository._connection.execute("EXPLAIN QUERY PLAN " + sql, args)
                ]
            frozen = canonical_json(snapshot)
        start = perf_counter()
        with UniverseRepository(path) as restart:
            assert canonical_json(restart.get(UniverseSnapshot, snapshot.fingerprint)) == frozen
        timings["restart_exact_reload"] = perf_counter() - start
        print("Completed restart_exact_reload", file=sys.stderr, flush=True)
        storage = path.stat().st_size
    output = io.StringIO()
    pstats.Stats(profiler, stream=output).sort_stats("cumulative").print_stats(12)
    return {
        "securities": securities,
        "seconds": timings,
        "counts": counts,
        "database_bytes": storage,
        "snapshot_bytes": len(frozen.encode()),
        "input_bytes": len(canonical_json(source).encode()),
        "audit_nodes": len(audit.lineage_ids),
        "audited_artifacts": artifact_count,
        "query_plans": plans,
        "profile": output.getvalue(),
        "snapshot_id": snapshot.fingerprint,
    }


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
