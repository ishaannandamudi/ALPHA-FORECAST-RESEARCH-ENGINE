"""Additive store 1.3, immutable security evidence and indexed frozen input sets."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, Self, TypeVar, cast

from afre.feature_store.models import (
    FeatureVintage,
    QualifiedHistoricalDelivery,
    SourceReference,
)
from afre.feature_store.repository import feature_store_schema
from afre.ids import validate_fingerprint
from afre.persistence import _schema_statements
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.target_engine.repository import TargetRepository, target_schema
from afre.target_engine.schema import TargetBounds
from afre.universe.calendars import UniverseCalendar, UniverseSession
from afre.universe.definitions import EligibilityPolicy, UniverseDefinition
from afre.universe.evidence import UniverseEvidence
from afre.universe.identity import ListingId, StableIssuerId, StableSecurityId
from afre.universe.lifecycle import LifecycleEvent, SecurityRelationship, TradabilityRecord
from afre.universe.listings import ListingRecord, SymbolAssignment
from afre.universe.membership import (
    ConstituentCoverage,
    MembershipSelection,
    UniverseMembershipVintage,
)
from afre.universe.models import (
    EligibilityResult,
    SecurityResolution,
    UniverseAudit,
    UniverseInputBuild,
    UniverseSnapshot,
)
from afre.universe.schema import UniverseBounds
from afre.universe.securities import ExternalIdentifier, IssuerRecord, SecurityRecord

RECORD_TYPES: tuple[type[Artifact], ...] = (
    IssuerRecord,
    SecurityRecord,
    ExternalIdentifier,
    ListingRecord,
    SymbolAssignment,
    LifecycleEvent,
    TradabilityRecord,
    SecurityRelationship,
    UniverseCalendar,
    UniverseMembershipVintage,
    ConstituentCoverage,
)
UNIVERSE_TYPES: tuple[type[Artifact], ...] = (
    *RECORD_TYPES,
    StableSecurityId,
    StableIssuerId,
    ListingId,
    UniverseSession,
    UniverseEvidence,
    EligibilityPolicy,
    UniverseDefinition,
    MembershipSelection,
    EligibilityResult,
    UniverseInputBuild,
    UniverseSnapshot,
    UniverseAudit,
    SecurityResolution,
    UniverseBounds,
)
U = TypeVar("U", bound=Artifact)


def universe_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE u_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT "
            "NOT NULL)"
        ),
        (
            "CREATE TABLE u_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, security_id TEXT, issuer_id TEXT, listing_id "
            "TEXT, owner_id TEXT, symbol TEXT, venue TEXT, start_ns INTEGER NOT "
            "NULL, end_ns INTEGER NOT NULL, known_ns INTEGER NOT NULL, "
            "knowledge_end_ns INTEGER NOT NULL, physical_ns INTEGER NOT NULL)"
        ),
        (
            "CREATE TABLE u_identities (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "kind TEXT NOT NULL, stable_id TEXT NOT NULL, UNIQUE(kind, stable_id))"
        ),
        (
            "CREATE TABLE u_definitions (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "name TEXT NOT NULL, version TEXT NOT NULL, UNIQUE(name, version))"
        ),
        (
            "CREATE TABLE u_build_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "build_id TEXT NOT NULL, record_id TEXT NOT NULL, UNIQUE(build_id, "
            "record_id))"
        ),
        (
            "CREATE TABLE u_build_features (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "build_id TEXT NOT NULL, vintage_id TEXT NOT NULL, UNIQUE(build_id, "
            "vintage_id))"
        ),
        (
            "CREATE TABLE u_snapshots (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "definition_id TEXT NOT NULL, valid_ns INTEGER NOT NULL, known_ns "
            "INTEGER NOT NULL, build_id TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE u_eligibility (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "definition_id TEXT NOT NULL, security_id TEXT NOT NULL, valid_ns "
            "INTEGER NOT NULL, known_ns INTEGER NOT NULL, build_id TEXT NOT NULL, "
            "state TEXT NOT NULL)"
        ),
        "CREATE INDEX u_record_cutoff_idx ON u_records (known_ns, type_name)",
        (
            "CREATE INDEX u_security_idx ON u_records (type_name, security_id, "
            "known_ns, start_ns, end_ns)"
        ),
        "CREATE INDEX u_issuer_idx ON u_records (issuer_id, known_ns, type_name)",
        (
            "CREATE INDEX u_listing_idx ON u_records (type_name, listing_id, "
            "known_ns, start_ns, end_ns)"
        ),
        (
            "CREATE INDEX u_membership_idx ON u_records (type_name, owner_id, "
            "security_id, known_ns, start_ns, end_ns)"
        ),
        (
            "CREATE INDEX u_symbol_idx ON u_records (type_name, symbol, venue, "
            "known_ns, start_ns, end_ns)"
        ),
        (
            "CREATE INDEX u_identifier_idx ON u_records (type_name, owner_id, "
            "known_ns, start_ns, end_ns)"
        ),
        "CREATE INDEX u_snapshot_idx ON u_snapshots (definition_id, valid_ns, known_ns)",
        (
            "CREATE INDEX u_eligibility_idx ON u_eligibility (definition_id, "
            "security_id, valid_ns, known_ns)"
        ),
    ]
    statements.append(
        "CREATE INDEX u_security_history_idx ON u_records (security_id, known_ns, start_ns)"
    )
    for table in (
        "u_artifacts",
        "u_records",
        "u_identities",
        "u_definitions",
        "u_build_records",
        "u_build_features",
        "u_snapshots",
        "u_eligibility",
    ):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE fingerprint = "
            f"NEW.fingerprint) BEGIN SELECT RAISE(ABORT, 'immutable AFRE "
            f"artifact'); END"
        )
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE "
                f"{operation} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable "
                f"AFRE artifact'); END"
            )
    return tuple(statements)


def evidence_of(value: Artifact) -> UniverseEvidence:
    require(type(value) in RECORD_TYPES, "universe evidence record required")
    evidence = getattr(value, "evidence", None)
    require(type(evidence) is UniverseEvidence, "typed universe evidence required")
    return cast(UniverseEvidence, evidence)


def record_index(value: Artifact) -> tuple[object, ...]:
    evidence = evidence_of(value)
    security = getattr(value, "security", None)
    issuer = getattr(value, "issuer", None)
    listing = getattr(value, "listing", None)
    owner = getattr(value, "definition_id", None)
    if isinstance(value, ExternalIdentifier):
        owner = value.kind.value + "|" + value.authority + "|" + value.value
    return (
        value.fingerprint,
        type(value).__name__,
        security.instrument.fingerprint if security is not None else None,
        issuer.instrument.fingerprint if issuer is not None else None,
        listing.fingerprint if listing is not None else None,
        owner,
        getattr(value, "symbol", None),
        getattr(value, "venue", None),
        evidence.validity.start_ns,
        evidence.validity.end_ns,
        evidence.clocks.final_available_ns,
        evidence.knowledge_until_ns,
        evidence.clocks.afre_computed_ns,
    )


def indexes(value: Artifact) -> tuple[tuple[str, tuple[object, ...]], ...]:
    answer = []
    if type(value) in RECORD_TYPES:
        answer.append(("u_records", record_index(value)))
    if isinstance(value, (IssuerRecord, SecurityRecord)):
        stable = (
            value.issuer.instrument
            if isinstance(value, IssuerRecord)
            else value.security.instrument
        )
        answer.append(
            ("u_identities", (value.fingerprint, type(value).__name__, stable.fingerprint))
        )
    if isinstance(value, UniverseDefinition):
        answer.append(("u_definitions", (value.fingerprint, value.name, value.version)))
    if isinstance(value, UniverseSnapshot):
        answer.append(
            (
                "u_snapshots",
                (
                    value.fingerprint,
                    value.definition.fingerprint,
                    value.valid_at_ns,
                    value.known_as_of_ns,
                    value.input_build_id,
                ),
            )
        )
    if isinstance(value, EligibilityResult):
        member = value.membership
        answer.append(
            (
                "u_eligibility",
                (
                    value.fingerprint,
                    member.definition_id,
                    member.security.instrument.fingerprint,
                    member.valid_at_ns,
                    member.known_as_of_ns,
                    member.input_build_id,
                    value.state.value,
                ),
            )
        )
    return tuple(answer)


class UniverseRepository(TargetRepository):
    # The strict pre-model interfaces retain their AFRE-4 snapshot metadata.
    _snapshot_engine_version: ClassVar[str] = "0.5.0"

    def __init__(self, path: str | Path, bounds: UniverseBounds | None = None) -> None:
        self._universe_identity_cache: dict[int, tuple[Artifact, str]] = {}
        self.universe_bounds = bounds or UniverseBounds()
        super().__init__(
            path,
            TargetBounds(
                serialized_bytes=self.universe_bounds.serialized_bytes,
                lineage_depth=self.universe_bounds.lineage_depth,
                lineage_nodes=self.universe_bounds.lineage_nodes,
            ),
        )

    def __enter__(self) -> Self:
        return self

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._universe_identity_cache.clear()

    def resolve(self, cls: type[U], identity: str) -> U:
        value = super().resolve(cls, identity)
        if self._validation_cache is not None:
            self._universe_identity_cache[id(value)] = (value, identity)
        return value

    def identity(self, value: Artifact) -> str:
        cached = self._universe_identity_cache.get(id(value))
        if cached is not None and cached[0] is value:
            return cached[1]
        return value.fingerprint

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in (0, 1, 2, 3, 4), "unknown future universe store version")
        if version == 4:
            return
        if version < 3:
            TargetRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 4:
                return
            require(version == 3, "unexpected universe migration version")
            TargetRepository._validate_layout(self)
            for statement in universe_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (
                    ("universe_store_schema_version", "1.3"),
                    ("universe_schema", "1.0"),
                    ("universe_engine_version", "0.4.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version = 4")

    def _validate_layout(self) -> None:
        expected = {
            statement.split()[2]: statement
            for statement in (
                *_schema_statements(),
                *feature_store_schema(),
                *target_schema(),
                *universe_schema(),
            )
        }
        actual = dict(
            self._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        require(actual == expected, "universe schema/index/trigger corruption")
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata"))
            == {
                "schema_version": "1.0",
                "engine_version": "0.1.0",
                "store_schema_version": "1.1",
                "feature_store_schema": "1.0",
                "feature_store_engine_version": "0.2.0",
                "target_store_schema_version": "1.2",
                "target_schema": "1.0",
                "target_engine_version": "0.3.0",
                "universe_store_schema_version": "1.3",
                "universe_schema": "1.0",
                "universe_engine_version": "0.4.0",
            },
            "universe metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 4,
            "universe integer schema corruption",
        )

    def _universe_bounds(self, value: Artifact) -> None:
        bounds = self.universe_bounds
        if isinstance(value, UniverseInputBuild):
            require(
                len(value.record_ids) + len(value.feature_ids) <= bounds.records,
                "universe input record bound",
            )
        elif isinstance(value, ConstituentCoverage):
            require(len(value.securities) <= bounds.securities, "universe security bound")
        elif isinstance(value, UniverseSnapshot):
            require(
                len(value.memberships) <= bounds.securities, "universe snapshot security bound"
            )
        elif isinstance(value, UniverseAudit):
            require(len(value.lineage_ids) <= bounds.lineage_nodes, "universe audit node bound")

    def put(self, value: Artifact) -> str:
        if type(value) not in UNIVERSE_TYPES:
            return super().put(value)
        require(
            self._in_transaction and not self._reading,
            "universe writes require writer transaction",
        )
        payload = canonical_json(value)
        require(
            len(payload.encode()) <= self.universe_bounds.serialized_bytes,
            "universe serialized byte bound",
        )
        require(deserialize(payload) == value, "universe canonical validation mismatch")
        self._universe_bounds(value)
        identity = value.fingerprint
        if self._connection.execute(
            "SELECT 1 FROM u_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            self.get(type(value), identity)
            return identity
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO u_artifacts VALUES (?, ?, ?, ?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        for table, values in indexes(value):
            self._connection.execute(
                f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
            )
        if isinstance(value, UniverseInputBuild):
            for table, column, identities in (
                ("u_build_records", "record_id", value.record_ids),
                ("u_build_features", "vintage_id", value.feature_ids),
            ):
                self._connection.executemany(
                    f"INSERT INTO {table} (fingerprint,build_id,{column}) VALUES (?, ?, ?)",
                    ((identity + "|" + item, identity, item) for item in identities),
                )
        return identity

    def get(self, cls: type[U], identity: str) -> U:
        if cls not in UNIVERSE_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM u_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "universe type/schema corruption")
        require(
            len(row[2].encode()) <= self.universe_bounds.serialized_bytes,
            "universe serialized byte bound",
        )
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity,
            "universe payload/fingerprint corruption",
        )
        self._universe_bounds(value)
        for table, values in indexes(value):
            require(
                self._connection.execute(
                    f"SELECT * FROM {table} WHERE fingerprint=?", (identity,)
                ).fetchone()
                == values,
                "universe temporal/identity index corruption",
            )
        if isinstance(value, UniverseInputBuild):
            for table, column, identities in (
                ("u_build_records", "record_id", value.record_ids),
                ("u_build_features", "vintage_id", value.feature_ids),
            ):
                actual = self._connection.execute(
                    (
                        f"SELECT fingerprint,{column} FROM {table} WHERE build_id=? "
                        f"ORDER BY {column}"
                    ),
                    (identity,),
                ).fetchall()
                require(
                    tuple(item[1] for item in actual) == identities
                    and all(key == identity + "|" + item for key, item in actual),
                    "universe frozen membership index corruption",
                )
        return cast(U, value)

    def get_any(self, identity: str) -> Artifact:
        if self._validation_cache is not None and identity in self._validation_cache:
            return self._validation_cache[identity]
        if not identity.startswith("afre.u_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM u_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {cls.__name__: cls for cls in UNIVERSE_TYPES}
        require(row is not None and row[0] in classes, "unresolved universe reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def master(self, cls: type[U], stable_id: str) -> U:
        row = self._connection.execute(
            "SELECT fingerprint FROM u_identities WHERE kind=? AND stable_id=?",
            (cls.__name__, stable_id),
        ).fetchone()
        if row is None:
            raise KeyError(stable_id)
        return self.resolve(cls, row[0])

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in UNIVERSE_TYPES:
            super()._validate_links(value)
            return
        if type(value) in RECORD_TYPES:
            evidence = evidence_of(value)
            self.resolve(SourceReference, evidence.source.fingerprint)
            if evidence.predecessor_id is not None:
                old = self.get_any(evidence.predecessor_id)
                from afre.universe.queries import revision_key

                require(
                    type(old) is type(value)
                    and revision_key(old) == revision_key(value)
                    and evidence_of(old).clocks.final_available_ns
                    <= evidence.clocks.final_available_ns,
                    "incompatible universe predecessor",
                )
            if isinstance(value, SecurityRecord):
                self.master(IssuerRecord, value.issuer.instrument.fingerprint)
            elif isinstance(
                value,
                (
                    ListingRecord,
                    SymbolAssignment,
                    LifecycleEvent,
                    TradabilityRecord,
                    ExternalIdentifier,
                    SecurityRelationship,
                    UniverseMembershipVintage,
                ),
            ):
                self.master(SecurityRecord, value.security.instrument.fingerprint)
            if isinstance(value, SecurityRelationship):
                if value.related_security is not None:
                    self.master(SecurityRecord, value.related_security.instrument.fingerprint)
                if value.issuer is not None:
                    self.master(IssuerRecord, value.issuer.instrument.fingerprint)
            if isinstance(value, (UniverseMembershipVintage, ConstituentCoverage)):
                definition = self.resolve(UniverseDefinition, value.definition_id)
                require(
                    evidence.source == definition.source,
                    "constituent source/definition mismatch",
                )
                if isinstance(value, ConstituentCoverage):
                    for security in value.securities:
                        self.master(SecurityRecord, security.instrument.fingerprint)
            if (
                isinstance(value, (SymbolAssignment, TradabilityRecord, SecurityRelationship))
                and value.listing is not None
            ):
                rows = self._connection.execute(
                    (
                        "SELECT fingerprint FROM u_records WHERE "
                        "type_name='ListingRecord' AND listing_id=? AND "
                        "security_id=?"
                    ),
                    (value.listing.fingerprint, value.security.instrument.fingerprint),
                ).fetchall()
                require(bool(rows), "listing/security reference mismatch")
                if isinstance(value, SymbolAssignment):
                    require(
                        any(
                            (listing := self.resolve(ListingRecord, row[0])).venue
                            == value.venue
                            and listing.evidence.validity.start_ns <= evidence.validity.start_ns
                            and listing.evidence.validity.end_ns >= evidence.validity.end_ns
                            for row in rows
                        ),
                        "symbol outside listing/venue interval",
                    )
        elif isinstance(value, UniverseDefinition):
            self.resolve(SourceReference, value.source.fingerprint)
            self.resolve(UniverseCalendar, value.calendar.fingerprint)
            for feature in (value.eligibility.price_feature, value.eligibility.volume_feature):
                if feature is not None:
                    self.resolve(type(feature), feature.fingerprint)
        elif isinstance(value, UniverseInputBuild):
            for identity in value.record_ids:
                evidence = evidence_of(self.get_any(identity))
                require(
                    evidence.clocks.final_available_ns <= value.known_as_of_ns
                    and evidence.clocks.afre_computed_ns <= value.constructed_ns,
                    "universe input backdated/future evidence",
                )
                self.approved(
                    evidence.clocks.historical_delivery,
                    value.query_policy.approved_delivery_attestors,
                )
            for identity in value.feature_ids:
                vintage = self.resolve(FeatureVintage, identity)
                require(
                    vintage.clocks.final_available_ns <= value.known_as_of_ns
                    and vintage.clocks.afre_computed_ns <= value.constructed_ns,
                    "universe market input backdated/future evidence",
                )
                self.approved(
                    vintage.clocks.historical_delivery,
                    value.query_policy.approved_delivery_attestors,
                )
        elif isinstance(value, (MembershipSelection, EligibilityResult, UniverseSnapshot)):
            from afre.universe.engine import replay_artifact

            require(
                replay_artifact(self, value) == value,
                "universe deterministic selection/calculation mismatch",
            )
        elif isinstance(value, UniverseAudit):
            snapshot = self.resolve(UniverseSnapshot, value.snapshot_id)
            require(
                value.eligibility in snapshot.eligibility
                and set(value.lineage_ids)
                == {x.fingerprint for x in self.lineage(value.eligibility.fingerprint)},
                "universe audit evidence mismatch",
            )

    @staticmethod
    def approved(proof: QualifiedHistoricalDelivery | None, attestors: tuple[str, ...]) -> None:
        if proof is not None:
            require(
                proof.attestor in attestors,
                "historical delivery attestor is not locally approved",
            )

    def lineage(self, identity: str) -> tuple[Artifact, ...]:
        if not identity.startswith("afre.u_"):
            return super().lineage(identity)
        from afre.universe.validation import lineage_edges

        answer = []
        seen: set[str] = set()
        active: set[str] = set()
        size = 0

        def visit(current: str, depth: int) -> None:
            nonlocal size
            require(current not in active, "universe lineage cycle")
            if current in seen:
                return
            require(
                depth <= self.universe_bounds.lineage_depth
                and len(seen) + len(active) < self.universe_bounds.lineage_nodes,
                "universe lineage depth/node bound",
            )
            active.add(current)
            if not current.startswith("afre.u_"):
                values = super(UniverseRepository, self).lineage(current)
                for item in values:
                    if item.fingerprint not in seen:
                        seen.add(item.fingerprint)
                        answer.append(item)
                        size += len(canonical_json(item).encode())
            else:
                value = self.get_any(current)
                for edge in sorted(set(lineage_edges(value))):
                    visit(edge, depth + 1)
                seen.add(current)
                answer.append(value)
                size += len(canonical_json(value).encode())
            active.remove(current)
            require(
                len(seen) <= self.universe_bounds.lineage_nodes, "universe lineage node bound"
            )
            require(
                size <= self.universe_bounds.serialized_bytes, "universe lineage byte bound"
            )

        visit(identity, 0)
        return tuple(answer)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            classes = {cls.__name__: cls for cls in UNIVERSE_TYPES}
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM u_artifacts"
            ):
                require(name in classes, "unknown universe family")
                self._validate_links(self.get(classes[name], identity))
                count += 1
            for table in (
                "u_records",
                "u_identities",
                "u_definitions",
                "u_snapshots",
                "u_eligibility",
            ):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} LEFT JOIN u_artifacts a "
                        f"ON {table}.fingerprint=a.fingerprint WHERE "
                        f"a.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan universe index",
                )
            for table, column, member_table in (
                ("u_build_records", "record_id", "u_records"),
                ("u_build_features", "vintage_id", "fs_vintages"),
            ):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} LEFT JOIN u_artifacts p "
                        f"ON {table}.build_id=p.fingerprint LEFT JOIN "
                        f"{member_table} m ON {table}.{column}=m.fingerprint "
                        f"WHERE p.fingerprint IS NULL OR m.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan universe input index",
                )
        return count
