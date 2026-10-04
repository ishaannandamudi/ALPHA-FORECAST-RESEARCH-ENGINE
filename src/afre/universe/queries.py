"""Indexed bitemporal queries over exact frozen input membership."""

from typing import TypeVar, cast

from afre.schema import Artifact, require
from afre.universe.definitions import UniverseDefinition
from afre.universe.identity import ListingId, StableIssuerId, StableSecurityId
from afre.universe.listings import ListingRecord, SymbolAssignment
from afre.universe.membership import (
    ConstituentCoverage,
    MembershipSelection,
    UniverseMembershipVintage,
)
from afre.universe.models import SecurityResolution, UniverseInputBuild
from afre.universe.repository import UniverseRepository, evidence_of
from afre.universe.schema import MembershipState, SnapshotCompleteness, UniverseSourceKind

R = TypeVar("R", bound=Artifact)


def revision_key(value: Artifact) -> tuple[object, ...]:
    fields: tuple[str, ...] = (
        "security",
        "issuer",
        "listing",
        "definition_id",
        "event_id",
        "symbol",
        "venue",
        "kind",
        "authority",
        "value",
        "related_security",
    )
    # Venue is temporal metadata on a listing; on a symbol it scopes the binding.
    if type(value).__name__ == "ListingRecord":
        fields = ("security", "listing")
    return (type(value), *(getattr(value, name, None) for name in fields))


def record_candidates(
    repository: UniverseRepository,
    cls: type[R],
    build_id: str,
    security: StableSecurityId | None = None,
    owner: str | None = None,
    listing: ListingId | None = None,
    symbol: str | None = None,
    venue: str | None = None,
    issuer: StableIssuerId | None = None,
) -> tuple[R, ...]:
    build = repository.resolve(UniverseInputBuild, build_id)
    sql = (
        "SELECT r.fingerprint FROM u_records r JOIN u_build_records b ON "
        "b.record_id=r.fingerprint AND b.build_id=? WHERE r.type_name=? AND "
        "r.known_ns<=?"
    )
    args: list[object] = [build_id, cls.__name__, build.known_as_of_ns]
    for column, value in (
        ("security_id", security.instrument.fingerprint if security else None),
        ("issuer_id", issuer.instrument.fingerprint if issuer else None),
        ("owner_id", owner),
        ("listing_id", listing.fingerprint if listing else None),
        ("symbol", symbol),
        ("venue", venue),
    ):
        if value is not None:
            sql += f" AND r.{column}=?"
            args.append(value)
    sql += " ORDER BY r.known_ns,r.fingerprint LIMIT ?"
    args.append(repository.universe_bounds.vintages + 1)
    rows = repository._connection.execute(sql, args).fetchall()
    require(len(rows) <= repository.universe_bounds.vintages, "universe vintage query bound")
    return tuple(repository.resolve(cls, row[0]) for row in rows)


def latest_records(repository: UniverseRepository, values: tuple[R, ...]) -> tuple[R, ...]:
    present = {repository.identity(value) for value in values}
    superseded: set[str] = set()
    for value in values:
        current = evidence_of(value).predecessor_id
        seen: set[str] = set()
        while current is not None:
            require(current not in seen, "universe revision cycle")
            require(
                len(seen) < repository.universe_bounds.lineage_depth,
                "universe revision depth bound",
            )
            seen.add(current)
            if current in present:
                superseded.add(current)
            current = evidence_of(repository.get_any(current)).predecessor_id
    return tuple(value for value in values if repository.identity(value) not in superseded)


def active_records(
    repository: UniverseRepository, values: tuple[R, ...], at_ns: int, known_ns: int
) -> tuple[R, ...]:
    return tuple(
        value
        for value in latest_records(repository, values)
        if evidence_of(value).known(known_ns) and evidence_of(value).validity.contains(at_ns)
    )


def precedence(values: tuple[R, ...]) -> tuple[R, ...]:
    if not values:
        return ()
    latest = max(evidence_of(value).clocks.final_available_ns for value in values)
    return tuple(
        value for value in values if evidence_of(value).clocks.final_available_ns == latest
    )


def coverage_as_of(
    repository: UniverseRepository,
    definition: UniverseDefinition,
    build_id: str,
    at_ns: int,
    known_ns: int,
) -> tuple[ConstituentCoverage | None, bool]:
    values = precedence(
        active_records(
            repository,
            record_candidates(
                repository, ConstituentCoverage, build_id, owner=definition.fingerprint
            ),
            at_ns,
            known_ns,
        )
    )
    return (values[0], False) if len(values) == 1 else (None, len(values) > 1)


def membership_as_of(
    repository: UniverseRepository,
    definition: UniverseDefinition,
    security: StableSecurityId,
    at_ns: int,
    known_ns: int,
    build_id: str,
) -> MembershipSelection:
    build = repository.resolve(UniverseInputBuild, build_id)
    require(build.known_as_of_ns == known_ns, "membership/build cutoff mismatch")
    coverage, conflict = coverage_as_of(repository, definition, build_id, at_ns, known_ns)
    all_values = latest_records(
        repository,
        record_candidates(
            repository, UniverseMembershipVintage, build_id, security, definition.fingerprint
        ),
    )
    values = precedence(
        tuple(
            value
            for value in all_values
            if value.evidence.known(known_ns) and value.evidence.validity.contains(at_ns)
        )
    )
    future = tuple(
        value.fingerprint
        for value in all_values
        if value.evidence.known(known_ns) and value.evidence.validity.start_ns > at_ns
    )
    states = {value.state for value in values}
    state = MembershipState.UNKNOWN
    if conflict or len(states) > 1:
        state = MembershipState.CONFLICTED
    elif states:
        state = next(iter(states))
    elif coverage is not None:
        if (
            definition.source_kind
            in (UniverseSourceKind.RULE_BASED, UniverseSourceKind.EXCHANGE_LISTING_SET)
            and security in coverage.securities
        ):
            state = MembershipState.INCLUDED
        elif coverage.completeness is SnapshotCompleteness.COMPLETE:
            state = MembershipState.EXCLUDED
    return MembershipSelection(
        definition.fingerprint,
        build_id,
        security,
        at_ns,
        known_ns,
        state,
        tuple(value.fingerprint for value in values),
        future,
        repository.identity(coverage) if coverage else None,
    )


def resolve_security(
    repository: UniverseRepository,
    symbol: str,
    venue: str,
    at_ns: int,
    known_ns: int,
    build_id: str,
) -> SecurityResolution:
    values = active_records(
        repository,
        record_candidates(repository, SymbolAssignment, build_id, symbol=symbol, venue=venue),
        at_ns,
        known_ns,
    )
    values = tuple(
        value
        for value in values
        if any(
            listing.venue == venue
            for listing in active_records(
                repository,
                record_candidates(
                    repository, ListingRecord, build_id, value.security, listing=value.listing
                ),
                at_ns,
                known_ns,
            )
        )
    )
    # All independent assignments matter: later evidence cannot resolve an
    # overlapping second listing/security by silently preferring a current mapping.
    pairs = {(value.security, value.listing) for value in values}
    security, listing = next(iter(pairs)) if len(pairs) == 1 else (None, None)
    return SecurityResolution(
        symbol,
        venue,
        at_ns,
        known_ns,
        security,
        listing,
        tuple(value.fingerprint for value in values),
        len(pairs) > 1,
    )


def typed_security(value: object) -> StableSecurityId:
    require(
        type(value) is StableSecurityId,
        "stable security identity required; symbol-only joins are forbidden",
    )
    return cast(StableSecurityId, value)
