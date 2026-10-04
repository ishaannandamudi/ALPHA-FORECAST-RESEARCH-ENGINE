"""Bounded snapshot construction, exact frozen replay and security-history APIs."""

from afre.feature_store.schema import QueryPolicy
from afre.schema import Artifact, require
from afre.serialization import canonical_json
from afre.time import validate_timestamp
from afre.universe.definitions import UniverseDefinition
from afre.universe.eligibility import evaluate
from afre.universe.identity import StableSecurityId
from afre.universe.membership import MembershipSelection, UniverseMembershipVintage
from afre.universe.models import (
    EligibilityResult,
    SecurityResolution,
    UniverseAudit,
    UniverseInputBuild,
    UniverseSnapshot,
)
from afre.universe.queries import (
    coverage_as_of,
    latest_records,
    membership_as_of,
    record_candidates,
    resolve_security,
    typed_security,
)
from afre.universe.repository import UniverseRepository
from afre.universe.schema import (
    UNIVERSE_BUILDER_VERSION,
    EligibilityState,
    MembershipState,
    SnapshotCompleteness,
)


def build_snapshot(
    repository: UniverseRepository,
    definition: UniverseDefinition,
    valid_at_ns: int,
    known_as_of_ns: int,
    input_build_id: str,
    constructed_ns: int,
) -> UniverseSnapshot:
    validate_timestamp(valid_at_ns)
    validate_timestamp(known_as_of_ns)
    validate_timestamp(constructed_ns)
    require(
        definition.implementation_version == UNIVERSE_BUILDER_VERSION,
        "unknown trusted universe builder",
    )
    build = repository.resolve(UniverseInputBuild, input_build_id)
    require(
        build.known_as_of_ns == known_as_of_ns and constructed_ns >= build.constructed_ns,
        "snapshot input cutoff/physical construction mismatch",
    )
    coverage, conflict = coverage_as_of(
        repository, definition, input_build_id, valid_at_ns, known_as_of_ns
    )
    sources = latest_records(
        repository,
        record_candidates(
            repository, UniverseMembershipVintage, input_build_id, owner=definition.fingerprint
        ),
    )
    candidates = set(coverage.securities if coverage else ())
    candidates.update(
        value.security for value in sources if value.evidence.known(known_as_of_ns)
    )
    require(
        len(candidates) <= repository.universe_bounds.securities,
        "universe snapshot security bound",
    )
    members = tuple(
        membership_as_of(
            repository, definition, security, valid_at_ns, known_as_of_ns, input_build_id
        )
        for security in sorted(candidates, key=lambda x: x.fingerprint)
    )
    eligible = tuple(evaluate(repository, definition, member) for member in members)
    completeness = coverage.completeness if coverage else SnapshotCompleteness.UNKNOWN
    if conflict or (
        completeness is SnapshotCompleteness.COMPLETE
        and any(
            member.state in (MembershipState.UNKNOWN, MembershipState.CONFLICTED)
            or result.state
            in (
                EligibilityState.UNKNOWN,
                EligibilityState.CONFLICTED,
                EligibilityState.NOT_AVAILABLE_YET,
            )
            for member, result in zip(members, eligible, strict=True)
        )
    ):
        completeness = SnapshotCompleteness.KNOWN_GAPS
    snapshot = UniverseSnapshot(
        definition,
        input_build_id,
        valid_at_ns,
        known_as_of_ns,
        constructed_ns,
        repository.identity(coverage) if coverage else None,
        completeness,
        members,
        eligible,
    )
    require(
        len(canonical_json(snapshot).encode()) <= repository.universe_bounds.serialized_bytes,
        "universe snapshot serialized byte bound",
    )
    return snapshot


def replay_artifact(repository: UniverseRepository, value: Artifact) -> Artifact:
    if isinstance(value, UniverseSnapshot):
        definition = repository.resolve(UniverseDefinition, value.definition.fingerprint)
        return build_snapshot(
            repository,
            definition,
            value.valid_at_ns,
            value.known_as_of_ns,
            value.input_build_id,
            value.constructed_ns,
        )
    member = value.membership if isinstance(value, EligibilityResult) else value
    require(isinstance(member, MembershipSelection), "universe replay family mismatch")
    assert isinstance(member, MembershipSelection)
    definition = repository.resolve(UniverseDefinition, member.definition_id)
    selected = membership_as_of(
        repository,
        definition,
        member.security,
        member.valid_at_ns,
        member.known_as_of_ns,
        member.input_build_id,
    )
    return (
        evaluate(repository, definition, selected)
        if isinstance(value, EligibilityResult)
        else selected
    )


class UniverseEngine:
    def __init__(
        self, repository: UniverseRepository, query_policy: QueryPolicy | None = None
    ) -> None:
        self.repository = repository
        self.query_policy = query_policy or QueryPolicy()

    def freeze_source(
        self, known_as_of_ns: int, constructed_ns: int | None = None
    ) -> UniverseInputBuild:
        validate_timestamp(known_as_of_ns)
        constructed = known_as_of_ns if constructed_ns is None else constructed_ns
        validate_timestamp(constructed)
        bounds = self.repository.universe_bounds
        with self.repository.transaction(), self.repository.validation_cache():
            records = self.repository._connection.execute(
                (
                    "SELECT fingerprint FROM u_records WHERE known_ns<=? ORDER BY "
                    "fingerprint LIMIT ?"
                ),
                (known_as_of_ns, bounds.records + 1),
            ).fetchall()
            features = self.repository._connection.execute(
                (
                    "SELECT fingerprint FROM fs_vintages WHERE available_ns<=? "
                    "ORDER BY fingerprint LIMIT ?"
                ),
                (known_as_of_ns, bounds.records + 1),
            ).fetchall()
            require(
                len(records) + len(features) <= bounds.records, "universe input record bound"
            )
            build = UniverseInputBuild(
                tuple(row[0] for row in records),
                tuple(row[0] for row in features),
                known_as_of_ns,
                constructed,
                self.query_policy,
            )
            self.repository.put(build)
        return build

    def universe_as_of(
        self,
        definition: UniverseDefinition,
        valid_at_ns: int,
        known_as_of_ns: int,
        input_build_id: str | None = None,
        constructed_ns: int | None = None,
    ) -> UniverseSnapshot:
        build = (
            self.freeze_source(known_as_of_ns, constructed_ns)
            if input_build_id is None
            else None
        )
        identity = build.fingerprint if build is not None else input_build_id
        assert identity is not None
        with self.repository.read_snapshot(), self.repository.validation_cache():
            stored = self.repository.resolve(UniverseDefinition, definition.fingerprint)
            require(stored == definition, "universe definition mismatch")
            source = self.repository.resolve(UniverseInputBuild, identity)
            return build_snapshot(
                self.repository,
                stored,
                valid_at_ns,
                known_as_of_ns,
                identity,
                source.constructed_ns if constructed_ns is None else constructed_ns,
            )

    def persist_snapshot(self, snapshot: UniverseSnapshot) -> str:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in snapshot.memberships:
                self.repository.put(value)
            for eligibility_result in snapshot.eligibility:
                self.repository.put(eligibility_result)
            return self.repository.put(snapshot)

    def membership_as_of(
        self,
        definition: UniverseDefinition,
        security: StableSecurityId,
        valid_at_ns: int,
        known_as_of_ns: int,
        input_build_id: str | None = None,
        constructed_ns: int | None = None,
    ) -> MembershipSelection:
        typed_security(security)
        validate_timestamp(valid_at_ns)
        build = (
            self.freeze_source(known_as_of_ns, constructed_ns)
            if input_build_id is None
            else None
        )
        identity = build.fingerprint if build else input_build_id
        assert identity is not None
        with self.repository.read_snapshot(), self.repository.validation_cache():
            stored = self.repository.resolve(UniverseDefinition, definition.fingerprint)
            return membership_as_of(
                self.repository, stored, security, valid_at_ns, known_as_of_ns, identity
            )

    def resolve_security(
        self,
        symbol: str,
        venue: str,
        valid_at_ns: int,
        known_as_of_ns: int,
        input_build_id: str | None = None,
        constructed_ns: int | None = None,
    ) -> SecurityResolution:
        validate_timestamp(valid_at_ns)
        validate_timestamp(known_as_of_ns)
        build = (
            self.freeze_source(known_as_of_ns, constructed_ns)
            if input_build_id is None
            else None
        )
        identity = build.fingerprint if build else input_build_id
        assert identity is not None
        with self.repository.read_snapshot(), self.repository.validation_cache():
            require(
                self.repository.resolve(UniverseInputBuild, identity).known_as_of_ns
                == known_as_of_ns,
                "resolution/build cutoff mismatch",
            )
            return resolve_security(
                self.repository, symbol, venue, valid_at_ns, known_as_of_ns, identity
            )

    def security_history(
        self, security: StableSecurityId, known_as_of_ns: int
    ) -> tuple[Artifact, ...]:
        typed_security(security)
        validate_timestamp(known_as_of_ns)
        with self.repository.read_snapshot():
            rows = self.repository._connection.execute(
                (
                    "SELECT fingerprint FROM u_records WHERE security_id=? AND "
                    "known_ns<=? ORDER BY start_ns,known_ns,fingerprint LIMIT ?"
                ),
                (
                    security.instrument.fingerprint,
                    known_as_of_ns,
                    self.repository.universe_bounds.vintages + 1,
                ),
            ).fetchall()
            require(
                len(rows) <= self.repository.universe_bounds.vintages,
                "security history vintage bound",
            )
            values = tuple(self.repository.get_any(row[0]) for row in rows)
        self._output_bound(values)
        return values

    def universe_history(
        self, definition: UniverseDefinition, known_as_of_ns: int
    ) -> tuple[UniverseMembershipVintage, ...]:
        build = self.freeze_source(known_as_of_ns)
        with self.repository.read_snapshot(), self.repository.validation_cache():
            values = record_candidates(
                self.repository,
                UniverseMembershipVintage,
                build.fingerprint,
                owner=definition.fingerprint,
            )
        self._output_bound(values)
        return values

    def snapshot_history(
        self, definition: UniverseDefinition, known_as_of_ns: int
    ) -> tuple[UniverseSnapshot, ...]:
        validate_timestamp(known_as_of_ns)
        with self.repository.read_snapshot():
            rows = self.repository._connection.execute(
                (
                    "SELECT fingerprint FROM u_snapshots WHERE definition_id=? AND "
                    "known_ns<=? ORDER BY valid_ns,known_ns,fingerprint LIMIT ?"
                ),
                (
                    definition.fingerprint,
                    known_as_of_ns,
                    self.repository.universe_bounds.snapshots + 1,
                ),
            ).fetchall()
            require(
                len(rows) <= self.repository.universe_bounds.snapshots, "snapshot history bound"
            )
            values = tuple(self.repository.get(UniverseSnapshot, row[0]) for row in rows)
        self._output_bound(values)
        return values

    def _output_bound(self, values: tuple[Artifact, ...]) -> None:
        require(
            sum(len(canonical_json(value).encode()) for value in values)
            <= self.repository.universe_bounds.serialized_bytes,
            "universe query byte bound",
        )

    def audit_security(self, snapshot_id: str, security: StableSecurityId) -> UniverseAudit:
        typed_security(security)
        with self.repository.read_snapshot():
            snapshot = self.repository.get(UniverseSnapshot, snapshot_id)
            result = next(
                value for value in snapshot.eligibility if value.membership.security == security
            )
            return UniverseAudit(
                snapshot_id,
                security,
                result,
                tuple(
                    value.fingerprint for value in self.repository.lineage(result.fingerprint)
                ),
            )

    def audit(self) -> int:
        return self.repository.audit()
