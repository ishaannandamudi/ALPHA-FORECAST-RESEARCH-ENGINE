"""Additive store 1.1 migration, immutable indexes and snapshot reads."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Self, TypeVar, cast

from afre.feature_store.dag import FeatureComputationGraph, FeatureComputationSpec
from afre.feature_store.materialization import (
    FeatureAudit,
    FeatureComputationReceipt,
    FeatureMaterialization,
    PointInTimeJoinResult,
)
from afre.feature_store.models import (
    AvailabilityEvidence,
    FeatureSetManifest,
    FeatureVintage,
    QualifiedHistoricalDelivery,
    RegisteredFeatureDefinition,
    ScopeBinding,
    SourceReference,
)
from afre.feature_store.normalization import NormalizationSpec, NormalizationState
from afre.feature_store.providers import MarketBar, SuppliedEIEFeatures
from afre.feature_store.schema import QueryBounds, QueryPolicy
from afre.features import DataQuality, MissingState
from afre.ids import validate_fingerprint
from afre.persistence import ArtifactStore, _schema_statements
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize

FS_TYPES: tuple[type[Artifact], ...] = (
    RegisteredFeatureDefinition,
    FeatureSetManifest,
    FeatureVintage,
    SourceReference,
    FeatureComputationSpec,
    FeatureComputationReceipt,
    FeatureComputationGraph,
    NormalizationSpec,
    NormalizationState,
    FeatureMaterialization,
    ScopeBinding,
    QualifiedHistoricalDelivery,
    AvailabilityEvidence,
    FeatureAudit,
    PointInTimeJoinResult,
    QueryBounds,
    QueryPolicy,
    MarketBar,
    SuppliedEIEFeatures,
)
A = TypeVar("A", bound=Artifact)


def feature_store_schema() -> tuple[str, ...]:
    statements = [
        "CREATE TABLE fs_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT NOT NULL)",
        "CREATE TABLE fs_definitions (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "name TEXT NOT NULL, version TEXT NOT NULL, foundation_id TEXT NOT NULL, "
        "UNIQUE(name, version), UNIQUE(foundation_id))",
        "CREATE TABLE fs_vintages (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "definition_id TEXT NOT NULL, entity_id TEXT NOT NULL, effective_ns INTEGER NOT NULL, "
        "valid_until_ns INTEGER, available_ns INTEGER NOT NULL, dataset_id TEXT NOT NULL, "
        "build_context TEXT NOT NULL, source_id TEXT NOT NULL, predecessor_id TEXT)",
        "CREATE TABLE fs_bindings (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "scope TEXT NOT NULL, security_id TEXT NOT NULL, entity_id TEXT NOT NULL, "
        "known_ns INTEGER NOT NULL, start_ns INTEGER NOT NULL, end_ns INTEGER NOT NULL)",
        "CREATE TABLE fs_receipts (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "output_id TEXT NOT NULL UNIQUE)",
        "CREATE TABLE fs_specs (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "output_id TEXT NOT NULL, logic_id TEXT NOT NULL)",
        "CREATE INDEX fs_pit_idx ON fs_vintages "
        "(definition_id, entity_id, available_ns DESC, effective_ns)",
        "CREATE INDEX fs_history_idx ON fs_vintages "
        "(definition_id, entity_id, effective_ns, available_ns)",
        "CREATE INDEX fs_dataset_idx ON fs_vintages (dataset_id, build_context, source_id)",
        "CREATE INDEX fs_predecessor_idx ON fs_vintages (predecessor_id)",
        "CREATE INDEX fs_scope_idx ON fs_bindings "
        "(scope, security_id, known_ns, start_ns, end_ns)",
        "CREATE INDEX fs_spec_idx ON fs_specs (output_id, logic_id)",
    ]
    for table in (
        "fs_artifacts",
        "fs_definitions",
        "fs_vintages",
        "fs_bindings",
        "fs_receipts",
        "fs_specs",
    ):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} "
            "WHERE fingerprint = NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} "
                f"BEFORE {operation} ON {table} BEGIN "
                "SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def indexed_values(value: Artifact) -> tuple[str, tuple[object, ...]] | None:
    if isinstance(value, RegisteredFeatureDefinition):
        return "fs_definitions", (
            value.fingerprint,
            value.definition.name,
            value.definition.version,
            value.definition.fingerprint,
        )
    if isinstance(value, FeatureVintage):
        return "fs_vintages", (
            value.fingerprint,
            value.feature.fingerprint,
            value.entity.fingerprint,
            value.effective_ns,
            value.valid_until_ns,
            value.clocks.final_available_ns,
            value.source.dataset_id,
            value.feature.build_context,
            value.source.fingerprint,
            value.predecessor_id,
        )
    if isinstance(value, ScopeBinding):
        return "fs_bindings", (
            value.fingerprint,
            value.scope.value,
            value.security.fingerprint,
            value.entity.fingerprint,
            value.known_ns,
            value.validity.start_ns,
            value.validity.end_ns,
        )
    if isinstance(value, FeatureComputationReceipt):
        return "fs_receipts", (value.fingerprint, value.output_id)
    if isinstance(value, FeatureComputationSpec):
        return "fs_specs", (value.fingerprint, value.output.fingerprint, value.logic_id)
    return None


class FeatureStoreRepository(ArtifactStore):
    def __enter__(self) -> Self:
        return self

    def __init__(self, path: str | Path, bounds: QueryBounds | None = None) -> None:
        self.bounds = bounds or QueryBounds()
        self._reading = False
        super().__init__(path)
        self._connection.execute("PRAGMA journal_mode = WAL")

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in (0, 1, 2), "unknown future feature-store version")
        if version == 2:
            return
        if version == 0:
            ArtifactStore._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 2:
                return
            require(version == 1, "unknown version during feature-store migration")
            ArtifactStore._validate_layout(self)
            for statement in feature_store_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (
                    ("store_schema_version", "1.1"),
                    ("feature_store_schema", "1.0"),
                    ("feature_store_engine_version", "0.2.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version = 2")

    def _validate_layout(self) -> None:
        expected = {
            statement.split()[2]: statement
            for statement in (*_schema_statements(), *feature_store_schema())
        }
        actual = {
            row[0]: row[1]
            for row in self._connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        }
        require(actual == expected, "feature-store layout/index/immutability corruption")
        require(
            dict(self._connection.execute("SELECT key, value FROM metadata"))
            == {
                "schema_version": "1.0",
                "engine_version": "0.1.0",
                "store_schema_version": "1.1",
                "feature_store_schema": "1.0",
                "feature_store_engine_version": "0.2.0",
            },
            "feature-store metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 2,
            "feature-store version mismatch",
        )

    @contextmanager
    def transaction(self) -> Iterator[None]:
        require(not self._reading, "writer transaction inside read snapshot")
        with super().transaction():
            yield

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        require(not self._reading and not self._in_transaction, "nested read/write snapshot")
        self._connection.execute("BEGIN")
        self._reading = True
        try:
            self._connection.execute("SELECT count(*) FROM fs_artifacts").fetchone()
            yield
            self._connection.execute("COMMIT")
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise
        finally:
            self._reading = False

    def close(self) -> None:
        require(not self._reading, "cannot close inside read snapshot")
        super().close()

    def put(self, artifact: Artifact) -> str:
        if type(artifact) not in FS_TYPES:
            return super().put(artifact)
        require(
            self._in_transaction and not self._reading,
            "writes require explicit writer transaction",
        )
        payload = canonical_json(artifact)
        require(
            len(payload.encode()) <= self.bounds.serialized_bytes,
            "serialized byte bound exceeded",
        )
        require(deserialize(payload) == artifact, "feature-store artifact validation mismatch")
        identity = artifact.fingerprint
        if self._connection.execute(
            "SELECT 1 FROM fs_artifacts WHERE fingerprint = ?", (identity,)
        ).fetchone():
            self.get(type(artifact), identity)
            return identity
        self._validate_links(artifact)
        self._connection.execute(
            "INSERT INTO fs_artifacts VALUES (?, ?, ?, ?)",
            (identity, type(artifact).__name__, "1.0", payload),
        )
        index = indexed_values(artifact)
        if index is not None:
            table, values = index
            self._connection.execute(
                f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
            )
        return identity

    def get(self, cls: type[A], identity: str) -> A:
        if cls not in FS_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name, schema_version, payload FROM fs_artifacts WHERE fingerprint = ?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(
            row[0] == cls.__name__ and row[1] == "1.0",
            "feature-store payload/type index mismatch",
        )
        require(
            len(row[2].encode()) <= self.bounds.serialized_bytes,
            "serialized byte bound exceeded",
        )
        artifact = deserialize(row[2])
        require(
            type(artifact) is cls and artifact.fingerprint == identity,
            "feature-store fingerprint corruption",
        )
        index = indexed_values(artifact)
        if index is not None:
            table, values = index
            actual = self._connection.execute(
                f"SELECT * FROM {table} WHERE fingerprint = ?", (identity,)
            ).fetchone()
            require(actual == values, "feature-store temporal/identity index corruption")
        return cast(A, artifact)

    def get_any(self, identity: str) -> Artifact:
        validate_fingerprint(identity)
        row = self._connection.execute(
            "SELECT type_name FROM fs_artifacts WHERE fingerprint = ?", (identity,)
        ).fetchone()
        require(row is not None, "unresolved feature-store lineage reference")
        assert row is not None
        classes = {cls.__name__: cls for cls in FS_TYPES}
        require(row[0] in classes, "unknown feature-store lineage family")
        return self.get(classes[row[0]], identity)

    def _validate_links(self, artifact: Artifact) -> None:
        if isinstance(artifact, (FeatureSetManifest, FeatureComputationGraph)):
            definitions = (
                artifact.definitions
                if isinstance(artifact, FeatureSetManifest)
                else artifact.nodes
            )
            for definition in definitions:
                require(
                    self.get(RegisteredFeatureDefinition, definition.fingerprint) == definition,
                    "unregistered feature set/graph definition",
                )
        elif isinstance(artifact, NormalizationSpec):
            self.get(RegisteredFeatureDefinition, artifact.feature.fingerprint)
        elif isinstance(artifact, FeatureAudit):
            self.get(RegisteredFeatureDefinition, artifact.feature.fingerprint)
            if artifact.selected is not None:
                require(
                    self.get(FeatureVintage, artifact.selected.fingerprint)
                    == artifact.selected,
                    "audit selected unresolved vintage",
                )
                self.lineage(artifact.selected.fingerprint)
            if artifact.scope_binding_id is not None:
                binding = self.get(ScopeBinding, artifact.scope_binding_id)
                require(
                    binding.security == artifact.origin.instrument
                    and binding.scope == artifact.feature.scope
                    and binding.known_ns <= artifact.origin.availability_cutoff_ns
                    and binding.validity.contains(artifact.origin.timestamp_ns)
                    and (
                        artifact.selected is None or binding.entity == artifact.selected.entity
                    ),
                    "audit scope relationship mismatch",
                )
        elif isinstance(artifact, PointInTimeJoinResult):
            for audit in artifact.audits:
                self._validate_links(audit)
        elif isinstance(artifact, FeatureMaterialization):
            for result in artifact.results:
                self._validate_links(result)
        elif isinstance(artifact, MarketBar):
            require(
                self.get(SourceReference, artifact.source.fingerprint) == artifact.source,
                "unregistered market bar source",
            )
        elif isinstance(artifact, SourceReference):
            if artifact.provenance.artifact_id.startswith("afre.fs_market_bar:"):
                self.get(MarketBar, artifact.provenance.artifact_id)
            for parent in artifact.parent_source_ids:
                self.get(SourceReference, parent)
                self.lineage(parent)
        elif isinstance(artifact, FeatureVintage):
            require(
                self.get(RegisteredFeatureDefinition, artifact.feature.fingerprint)
                == artifact.feature,
                "unregistered vintage definition",
            )
            require(
                self.get(SourceReference, artifact.source.fingerprint) == artifact.source,
                "unregistered source reference",
            )
            self.lineage(artifact.source.fingerprint)
            if artifact.predecessor_id is not None:
                predecessor = self.get(FeatureVintage, artifact.predecessor_id)
                require(
                    predecessor.feature == artifact.feature
                    and predecessor.entity == artifact.entity
                    and predecessor.effective_ns == artifact.effective_ns
                    and predecessor.valid_until_ns == artifact.valid_until_ns
                    and predecessor.clocks.final_available_ns
                    <= artifact.clocks.final_available_ns,
                    "incompatible/future revision predecessor",
                )
                self.lineage(predecessor.fingerprint)
            for identity in artifact.input_ids:
                dependency = self.get(FeatureVintage, identity)
                require(
                    dependency.feature.definition.fingerprint
                    in artifact.feature.definition.dependency_ids,
                    "undeclared vintage dependency",
                )
                require(dependency.entity == artifact.entity, "cross-entity computation input")
                require(
                    dependency.clocks.final_available_ns <= artifact.clocks.final_available_ns,
                    "future computation dependency",
                )
                self.lineage(identity)
            if artifact.computation_spec_id is not None:
                spec = self.get(FeatureComputationSpec, artifact.computation_spec_id)
                require(
                    spec.output == artifact.feature
                    and spec.normalization_state_id == artifact.normalization_state_id,
                    "vintage computation specification mismatch",
                )
            if artifact.normalization_state_id is not None:
                state = self.get(NormalizationState, artifact.normalization_state_id)
                require(
                    state.available_ns <= artifact.clocks.final_available_ns,
                    "future normalization state",
                )
        elif isinstance(artifact, FeatureComputationSpec):
            for feature in (artifact.output, *artifact.inputs):
                self.get(RegisteredFeatureDefinition, feature.fingerprint)
            existing = self._connection.execute(
                "SELECT fingerprint FROM fs_specs WHERE output_id = ?",
                (artifact.output.fingerprint,),
            ).fetchall()
            require(
                all(
                    self.get(FeatureComputationSpec, identity).logic_id == artifact.logic_id
                    for (identity,) in existing
                ),
                "changed computation logic requires a new definition revision",
            )
            if artifact.normalization_state_id is not None:
                state = self.get(NormalizationState, artifact.normalization_state_id)
                require(
                    state.spec.feature == artifact.inputs[0], "normalization feature mismatch"
                )
        elif isinstance(artifact, NormalizationState):
            self.get(NormalizationSpec, artifact.spec.fingerprint)
            for identity in artifact.fit_sample_ids:
                sample = self.get(FeatureVintage, identity)
                require(
                    sample.feature == artifact.spec.feature
                    and sample.source.dataset_id == artifact.source_dataset_id,
                    "normalization fit sample mismatch",
                )
                require(
                    sample.clocks.final_available_ns <= artifact.fit_cutoff_ns
                    and sample.effective_ns <= artifact.fit_cutoff_ns,
                    "normalization fit sample uses future observation",
                )
                require(
                    sample.state is MissingState.PRESENT
                    and sample.quality is DataQuality.VERIFIED,
                    "normalization fit sample is absent or unverified",
                )
                self.lineage(identity)
        elif isinstance(artifact, FeatureComputationReceipt):
            output = self.get(FeatureVintage, artifact.output_id)
            require(
                output.computation_spec_id == artifact.spec.fingerprint
                and output.input_ids == artifact.input_ids
                and output.normalization_state_id == artifact.normalization_state_id
                and output.effective_ns == artifact.origin.timestamp_ns,
                "receipt/output lineage mismatch",
            )
            require(
                artifact.computation_available_ns == output.clocks.availability_floor_ns,
                "receipt/output computation clock mismatch",
            )
            for identity in artifact.input_ids:
                value = self.get(FeatureVintage, identity)
                require(
                    value.clocks.final_available_ns <= artifact.origin.availability_cutoff_ns,
                    "receipt uses future input at origin",
                )
                require(value.feature in artifact.spec.inputs, "receipt undeclared input")
            if artifact.normalization_state_id is not None:
                state = self.get(NormalizationState, artifact.normalization_state_id)
                require(
                    state.fit_cutoff_ns <= artifact.origin.availability_cutoff_ns
                    and state.available_ns <= artifact.origin.availability_cutoff_ns,
                    "receipt uses future normalization state at origin",
                )

    def lineage(self, identity: str) -> tuple[Artifact, ...]:
        seen: set[str] = set()
        active: set[str] = set()
        results: list[Artifact] = []

        def visit(current: str, depth: int) -> None:
            require(depth <= self.bounds.lineage_depth, "lineage depth bound exceeded")
            require(current not in active, "lineage cycle detected")
            if current in seen:
                return
            require(
                len(seen) + len(active) < self.bounds.lineage_nodes,
                "lineage node bound exceeded",
            )
            active.add(current)
            value = self.get_any(current)
            edges: tuple[str, ...] = ()
            if isinstance(value, SourceReference):
                edges = value.parent_source_ids
                if value.provenance.artifact_id.startswith("afre.fs_market_bar:"):
                    edges += (value.provenance.artifact_id,)
            elif isinstance(value, MarketBar):
                edges = (value.source.fingerprint,)
            elif isinstance(value, FeatureVintage):
                edges = (value.source.fingerprint, *value.input_ids)
                if value.predecessor_id is not None:
                    edges += (value.predecessor_id,)
                if value.normalization_state_id is not None:
                    edges += (value.normalization_state_id,)
                if value.computation_spec_id is not None:
                    edges += (value.computation_spec_id,)
                    receipt = self.receipt_for(value.fingerprint)
                    require(receipt is not None, "computed vintage lacks a computation receipt")
                    assert receipt is not None
                    edges += (receipt.fingerprint,)
            elif isinstance(value, NormalizationState):
                edges = value.fit_sample_ids
            elif isinstance(value, FeatureComputationReceipt):
                edges = value.input_ids
            for edge in sorted(edges):
                visit(edge, depth + 1)
            active.remove(current)
            seen.add(current)
            results.append(value)

        visit(identity, 0)
        require(
            sum(len(canonical_json(value).encode()) for value in results)
            <= self.bounds.serialized_bytes,
            "lineage serialized byte bound exceeded",
        )
        return tuple(results)

    def receipt_for(self, output_id: str) -> FeatureComputationReceipt | None:
        row = self._connection.execute(
            "SELECT fingerprint FROM fs_receipts WHERE output_id = ?", (output_id,)
        ).fetchone()
        return None if row is None else self.get(FeatureComputationReceipt, row[0])

    def audit(self) -> int:
        count = super().audit()
        classes = {cls.__name__: cls for cls in FS_TYPES}
        for identity, name in self._connection.execute(
            "SELECT fingerprint, type_name FROM fs_artifacts"
        ):
            require(name in classes, "unknown persisted feature-store family")
            artifact = self.get(classes[name], identity)
            self._validate_links(artifact)
            if isinstance(artifact, (FeatureVintage, SourceReference, NormalizationState)):
                self.lineage(identity)
            count += 1
        for table in (
            "fs_definitions",
            "fs_vintages",
            "fs_bindings",
            "fs_receipts",
            "fs_specs",
        ):
            orphan = self._connection.execute(
                f"SELECT count(*) FROM {table} LEFT JOIN fs_artifacts "
                f"ON {table}.fingerprint = fs_artifacts.fingerprint "
                "WHERE fs_artifacts.fingerprint IS NULL"
            ).fetchone()[0]
            require(orphan == 0, "orphan feature-store index")
        return count
