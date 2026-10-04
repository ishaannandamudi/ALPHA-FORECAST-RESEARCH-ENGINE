"""Additive store 1.2 migration and immutable target-specific indexes."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Self, TypeVar, cast

from afre.datasets import UniverseManifest
from afre.feature_store.models import SourceReference
from afre.feature_store.repository import FeatureStoreRepository, feature_store_schema
from afre.feature_store.schema import QueryBounds
from afre.ids import validate_fingerprint
from afre.persistence import _schema_statements
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.target_engine.corporate_actions import TargetActionStream, TargetCorporateAction
from afre.target_engine.definitions import (
    TargetDefinition,
    TargetEndpointRules,
    TargetPathPolicy,
    TargetSetManifest,
)
from afre.target_engine.market_data import TargetBar, TargetMarketSource, TargetSourceBuild
from afre.target_engine.models import TargetAudit, TargetDatasetManifest, TargetVintage
from afre.target_engine.quality import TargetQuality
from afre.target_engine.residuals import BenchmarkReference, SuppliedBenchmarkReturn
from afre.target_engine.schema import TargetBounds
from afre.target_engine.windows import TargetCalendar, TargetSession

TARGET_TYPES: tuple[type[Artifact], ...] = (
    TargetBounds,
    TargetDefinition,
    TargetEndpointRules,
    TargetPathPolicy,
    TargetSetManifest,
    TargetBar,
    TargetMarketSource,
    TargetSourceBuild,
    TargetCalendar,
    TargetSession,
    TargetCorporateAction,
    TargetActionStream,
    BenchmarkReference,
    SuppliedBenchmarkReturn,
    TargetVintage,
    TargetDatasetManifest,
    TargetQuality,
    TargetAudit,
)
A = TypeVar("A", bound=Artifact)


def target_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE target_artifacts (fingerprint TEXT PRIMARY KEY NOT "
            "NULL, type_name TEXT NOT NULL, schema_version TEXT NOT NULL, "
            "payload TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE target_definitions (fingerprint TEXT PRIMARY KEY "
            "NOT NULL, name TEXT NOT NULL, version TEXT NOT NULL, "
            "UNIQUE(name, version))"
        ),
        (
            "CREATE TABLE target_bars (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "source_id TEXT NOT NULL, instrument_id TEXT NOT NULL, end_ns "
            "INTEGER NOT NULL, available_ns INTEGER NOT NULL, predecessor_id "
            "TEXT)"
        ),
        (
            "CREATE TABLE target_build_bars (fingerprint TEXT PRIMARY KEY NOT "
            "NULL, build_id TEXT NOT NULL, bar_id TEXT NOT NULL, "
            "instrument_id TEXT NOT NULL, end_ns INTEGER NOT NULL, "
            "UNIQUE(build_id, bar_id))"
        ),
        (
            "CREATE TABLE target_vintages (fingerprint TEXT PRIMARY KEY NOT "
            "NULL, definition_id TEXT NOT NULL, instrument_id TEXT NOT NULL, "
            "origin_ns INTEGER NOT NULL, origin_id TEXT NOT NULL, end_ns INTEGER, "
            "available_ns INTEGER "
            "NOT NULL, source_build_id TEXT NOT NULL, state TEXT NOT NULL, "
            "quality TEXT NOT NULL, benchmark_id TEXT)"
        ),
        (
            "CREATE TABLE target_datasets (fingerprint TEXT PRIMARY KEY NOT "
            "NULL, target_set_id TEXT NOT NULL, source_build_id TEXT NOT "
            "NULL, cutoff_ns INTEGER NOT NULL)"
        ),
        (
            "CREATE TABLE target_dataset_rows (fingerprint TEXT PRIMARY KEY "
            "NOT NULL, dataset_id TEXT NOT NULL, row_id TEXT NOT NULL, "
            "UNIQUE(dataset_id, row_id))"
        ),
        (
            "CREATE INDEX target_source_idx ON target_bars (source_id, "
            "available_ns, instrument_id, end_ns)"
        ),
        "CREATE INDEX target_bar_idx ON target_build_bars (build_id, instrument_id, end_ns)",
        (
            "CREATE INDEX target_known_idx ON target_vintages (definition_id, "
            "available_ns, instrument_id, origin_ns)"
        ),
        (
            "CREATE INDEX target_origin_idx ON target_vintages "
            "(definition_id, instrument_id, origin_ns, available_ns)"
        ),
        (
            "CREATE INDEX target_interval_idx ON target_vintages (origin_ns, "
            "end_ns, available_ns)"
        ),
        (
            "CREATE INDEX target_exact_origin_idx ON target_vintages "
            "(definition_id, origin_id, available_ns)"
        ),
        (
            "CREATE INDEX target_build_idx ON target_vintages "
            "(source_build_id, definition_id, benchmark_id)"
        ),
        (
            "CREATE INDEX target_set_idx ON target_datasets (target_set_id, "
            "cutoff_ns, source_build_id)"
        ),
    ]
    for table in (
        "target_artifacts",
        "target_definitions",
        "target_bars",
        "target_build_bars",
        "target_vintages",
        "target_datasets",
        "target_dataset_rows",
    ):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE fingerprint = NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} "
                f"BEFORE {operation} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def target_index(value: Artifact) -> tuple[str, tuple[object, ...]] | None:
    if isinstance(value, TargetDefinition):
        return "target_definitions", (value.fingerprint, value.name, value.version)
    if isinstance(value, TargetBar):
        return "target_bars", (
            value.fingerprint,
            value.source.fingerprint,
            value.instrument.fingerprint,
            value.period.end_ns,
            value.clocks.final_available_ns,
            value.predecessor_id,
        )
    if isinstance(value, TargetVintage):
        return "target_vintages", (
            value.fingerprint,
            value.definition.fingerprint,
            value.origin.instrument.fingerprint,
            value.origin.timestamp_ns,
            value.origin.fingerprint,
            value.window.end_ns if value.window else None,
            value.clocks.final_available_ns,
            value.source_build_id,
            value.state.value,
            value.quality.source_quality.value,
            value.benchmark_id,
        )
    if isinstance(value, TargetDatasetManifest):
        return "target_datasets", (
            value.fingerprint,
            value.targets.fingerprint,
            value.source_build_id,
            value.build_cutoff_ns,
        )
    return None


class TargetRepository(FeatureStoreRepository):
    def __init__(self, path: str | Path, bounds: TargetBounds | None = None) -> None:
        self.target_bounds = bounds or TargetBounds()
        self._validation_cache: dict[str, Artifact] | None = None
        self._membership_cache: dict[str, set[str]] = {}
        self._source_ids: dict[int, str] = {}
        super().__init__(
            path,
            QueryBounds(
                serialized_bytes=self.target_bounds.serialized_bytes,
                lineage_depth=self.target_bounds.lineage_depth,
                lineage_nodes=self.target_bounds.lineage_nodes,
            ),
        )

    def __enter__(self) -> Self:
        return self

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in (0, 1, 2, 3), "unknown future target store version")
        if version == 3:
            return
        if version < 2:
            FeatureStoreRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 3:
                return
            require(version == 2, "unexpected target migration version")
            FeatureStoreRepository._validate_layout(self)
            for statement in target_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (
                    ("target_store_schema_version", "1.2"),
                    ("target_schema", "1.0"),
                    ("target_engine_version", "0.3.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version = 3")

    def _validate_layout(self) -> None:
        expected = {
            statement.split()[2]: statement
            for statement in (*_schema_statements(), *feature_store_schema(), *target_schema())
        }
        actual = dict(
            self._connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        require(actual == expected, "target store schema/index/trigger corruption")
        require(
            dict(self._connection.execute("SELECT key, value FROM metadata"))
            == {
                "schema_version": "1.0",
                "engine_version": "0.1.0",
                "store_schema_version": "1.1",
                "feature_store_schema": "1.0",
                "feature_store_engine_version": "0.2.0",
                "target_store_schema_version": "1.2",
                "target_schema": "1.0",
                "target_engine_version": "0.3.0",
            },
            "target store metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 3,
            "target store integer version mismatch",
        )

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        require(self._validation_cache is None, "nested target validation cache")
        require(
            self._reading or self._in_transaction, "validation cache requires pinned snapshot"
        )
        self._validation_cache = {}
        try:
            yield
        finally:
            self._validation_cache = None
            self._membership_cache.clear()
            self._source_ids.clear()

    def resolve(self, cls: type[A], identity: str) -> A:
        if self._validation_cache is not None and identity in self._validation_cache:
            value = self._validation_cache[identity]
            require(type(value) is cls, "cached target family mismatch")
            return cast(A, value)
        value = self.get(cls, identity)
        if self._validation_cache is not None:
            self._validation_cache[identity] = value
            if isinstance(value, TargetSourceBuild):
                self._source_ids[id(value)] = identity
        return value

    def source_identity(self, build: TargetSourceBuild) -> str:
        """Reuse only a validated immutable build in the current pinned snapshot."""
        identity = self._source_ids.get(id(build))
        if (
            identity is not None
            and self._validation_cache is not None
            and self._validation_cache.get(identity) is build
        ):
            return identity
        return build.fingerprint

    def put(self, artifact: Artifact) -> str:
        if type(artifact) not in TARGET_TYPES:
            return super().put(artifact)
        require(
            self._in_transaction and not self._reading,
            "target writes require writer transaction",
        )
        payload = canonical_json(artifact)
        require(
            len(payload.encode()) <= self.target_bounds.serialized_bytes,
            "target serialized byte bound",
        )
        require(deserialize(payload) == artifact, "target canonical validation mismatch")
        self._check_target_bounds(artifact)
        identity = artifact.fingerprint
        if self._connection.execute(
            "SELECT 1 FROM target_artifacts WHERE fingerprint = ?", (identity,)
        ).fetchone():
            self.get(type(artifact), identity)
            return identity
        self._validate_links(artifact)
        self._connection.execute(
            "INSERT INTO target_artifacts VALUES (?, ?, ?, ?)",
            (identity, type(artifact).__name__, "1.0", payload),
        )
        index = target_index(artifact)
        if index is not None:
            table, values = index
            self._connection.execute(
                f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
            )
        if isinstance(artifact, TargetSourceBuild):
            for bar_id in artifact.bar_ids:
                bar = self.resolve(TargetBar, bar_id)
                self._connection.execute(
                    "INSERT INTO target_build_bars VALUES (?, ?, ?, ?, ?)",
                    (
                        identity + "|" + bar_id,
                        identity,
                        bar_id,
                        bar.instrument.fingerprint,
                        bar.period.end_ns,
                    ),
                )
        if isinstance(artifact, TargetDatasetManifest):
            self._connection.executemany(
                "INSERT INTO target_dataset_rows VALUES (?, ?, ?)",
                ((identity + "|" + row_id, identity, row_id) for row_id in artifact.row_ids),
            )
        return identity

    def _check_target_bounds(self, artifact: Artifact) -> None:
        bounds = self.target_bounds
        if isinstance(artifact, TargetSourceBuild):
            require(
                len(artifact.bar_ids) <= bounds.source_observations, "source observation bound"
            )
        elif isinstance(artifact, TargetDatasetManifest):
            require(
                len(artifact.origins) <= bounds.origins
                and len({value.instrument for value in artifact.origins}) <= bounds.instruments
                and len(artifact.targets.definitions) <= bounds.targets
                and len(artifact.row_ids) <= bounds.rows,
                "target dataset bounds exceeded",
            )
        elif isinstance(artifact, TargetSetManifest):
            require(len(artifact.definitions) <= bounds.targets, "target definition bound")
        elif isinstance(artifact, TargetVintage):
            require(len(artifact.path_ids) <= bounds.path_observations, "target path bound")
        elif isinstance(artifact, TargetAudit):
            require(
                len(artifact.lineage_ids) <= bounds.lineage_nodes, "target audit node bound"
            )

    def get(self, cls: type[A], identity: str) -> A:
        if cls not in TARGET_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            (
                "SELECT type_name, schema_version, payload FROM target_artifacts "
                "WHERE fingerprint = ?"
            ),
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(
            row[0] == cls.__name__ and row[1] == "1.0", "target type/schema index corruption"
        )
        require(
            len(row[2].encode()) <= self.target_bounds.serialized_bytes,
            "target serialized byte bound",
        )
        artifact = deserialize(row[2])
        self._check_target_bounds(artifact)
        require(
            type(artifact) is cls and artifact.fingerprint == identity,
            "target fingerprint/payload corruption",
        )
        index = target_index(artifact)
        if index is not None:
            table, values = index
            require(
                self._connection.execute(
                    f"SELECT * FROM {table} WHERE fingerprint = ?", (identity,)
                ).fetchone()
                == values,
                "target temporal/identity index corruption",
            )
        if isinstance(artifact, TargetSourceBuild):
            actual = self._connection.execute(
                (
                    "SELECT fingerprint, bar_id, instrument_id, end_ns FROM "
                    "target_build_bars WHERE build_id = ? ORDER BY bar_id"
                ),
                (identity,),
            ).fetchall()
            require(
                tuple(item[1] for item in actual) == artifact.bar_ids,
                "source build membership index corruption",
            )
            for key, bar_id, instrument, end_ns in actual:
                indexed = self._connection.execute(
                    "SELECT instrument_id, end_ns FROM target_bars WHERE fingerprint = ?",
                    (bar_id,),
                ).fetchone()
                require(
                    key == identity + "|" + bar_id and indexed == (instrument, end_ns),
                    "source build bar index corruption",
                )
        if isinstance(artifact, TargetDatasetManifest):
            actual = self._connection.execute(
                (
                    "SELECT fingerprint, row_id FROM target_dataset_rows WHERE "
                    "dataset_id = ? ORDER BY row_id"
                ),
                (identity,),
            ).fetchall()
            require(
                tuple(item[1] for item in actual) == artifact.row_ids
                and all(key == identity + "|" + row_id for key, row_id in actual),
                "target dataset membership index corruption",
            )
        return cast(A, artifact)

    def get_any(self, identity: str) -> Artifact:
        validate_fingerprint(identity)
        if identity.startswith("afre.universe_manifest:"):
            return self.get(UniverseManifest, identity)
        if not identity.startswith("afre.target_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM target_artifacts WHERE fingerprint = ?", (identity,)
        ).fetchone()
        classes = {cls.__name__: cls for cls in TARGET_TYPES}
        require(row is not None and row[0] in classes, "unresolved target lineage reference")
        assert row is not None
        return self.get(classes[row[0]], identity)

    def _validate_links(self, artifact: Artifact) -> None:
        if type(artifact) not in TARGET_TYPES:
            super()._validate_links(artifact)
            return
        if isinstance(artifact, TargetMarketSource):
            self.resolve(SourceReference, artifact.upstream.fingerprint)
        elif isinstance(artifact, TargetDefinition):
            if artifact.benchmark is not None:
                self.resolve(BenchmarkReference, artifact.benchmark.fingerprint)
        elif isinstance(artifact, TargetSetManifest):
            for definition in artifact.definitions:
                self.resolve(TargetDefinition, definition.fingerprint)
        elif isinstance(artifact, TargetBar):
            self.resolve(TargetMarketSource, artifact.source.fingerprint)
            if artifact.predecessor_id is not None:
                old_bar = self.resolve(TargetBar, artifact.predecessor_id)
                require(
                    old_bar.source == artifact.source
                    and old_bar.instrument == artifact.instrument
                    and old_bar.period == artifact.period
                    and old_bar.timestamp_convention == artifact.timestamp_convention
                    and old_bar.clocks.final_available_ns <= artifact.clocks.final_available_ns,
                    "incompatible/future target bar predecessor",
                )
        elif isinstance(artifact, (TargetCorporateAction, SuppliedBenchmarkReturn)):
            if artifact.predecessor_id is not None:
                old = self.resolve(type(artifact), artifact.predecessor_id)
                if isinstance(artifact, TargetCorporateAction):
                    assert isinstance(old, TargetCorporateAction)
                    compatible = (
                        old.instrument == artifact.instrument
                        and old.event_id == artifact.event_id
                        and old.dataset_id == artifact.dataset_id
                        and old.effective_ns == artifact.effective_ns
                    )
                else:
                    assert isinstance(old, SuppliedBenchmarkReturn)
                    compatible = (
                        old.benchmark == artifact.benchmark
                        and old.window == artifact.window
                        and old.origin_price_ns == artifact.origin_price_ns
                        and old.endpoint_price_ns == artifact.endpoint_price_ns
                    )
                require(
                    compatible
                    and old.clocks.final_available_ns <= artifact.clocks.final_available_ns,
                    "incompatible target source predecessor",
                )
            if isinstance(artifact, SuppliedBenchmarkReturn):
                self.resolve(BenchmarkReference, artifact.benchmark.fingerprint)
        elif isinstance(artifact, TargetActionStream):
            for identity in artifact.action_ids:
                action = self.resolve(TargetCorporateAction, identity)
                require(
                    action.dataset_id == artifact.dataset_id
                    and action.clocks.final_available_ns <= artifact.clocks.final_available_ns,
                    "future/incompatible action stream member",
                )
        elif isinstance(artifact, TargetSourceBuild):
            self.resolve(TargetMarketSource, artifact.source.fingerprint)
            self.resolve(TargetCalendar, artifact.calendar.fingerprint)
            require(
                len(artifact.bar_ids) <= self.target_bounds.source_observations,
                "source observation bound exceeded",
            )
            sessions = {item.session_id: item for item in artifact.calendar.sessions}
            for identity in artifact.bar_ids:
                bar = self.resolve(TargetBar, identity)
                require(
                    bar.source == artifact.source
                    and bar.clocks.final_available_ns <= artifact.known_as_of_ns,
                    "future/incompatible bar in source build",
                )
                session = sessions.get(bar.session_id)
                require(
                    session is not None
                    and session.period.start_ns <= bar.period.start_ns
                    and session.period.end_ns >= bar.period.end_ns
                    and (bar.period.end_ns - session.period.start_ns) % bar.source.interval_ns
                    == 0,
                    "target bar outside declared calendar/grid",
                )
            if artifact.action_stream is not None:
                self.resolve(TargetActionStream, artifact.action_stream.fingerprint)
            for identity in artifact.benchmark_ids:
                benchmark = self.resolve(SuppliedBenchmarkReturn, identity)
                require(
                    benchmark.clocks.final_available_ns <= artifact.known_as_of_ns,
                    "future benchmark in build",
                )
        elif isinstance(artifact, TargetVintage):
            self.resolve(TargetDefinition, artifact.definition.fingerprint)
            build = self.resolve(TargetSourceBuild, artifact.source_build_id)
            require(
                artifact.clocks.afre_computed_ns >= build.known_as_of_ns,
                "target computation before build cutoff",
            )
            require(
                artifact.definition.calendar_id == build.source.calendar_id
                and artifact.definition.bar_definition == build.source.bar_definition
                and build.source.upstream.dataset_id in artifact.definition.source_dataset_ids,
                "target/source build context mismatch",
            )
            build_id = self.source_identity(build)
            if build_id not in self._membership_cache:
                self._membership_cache[build_id] = set(build.bar_ids)
            members = self._membership_cache[build_id]
            bars = tuple(
                dict.fromkeys(
                    (artifact.origin_bar_id, artifact.endpoint_bar_id, *artifact.path_ids)
                )
            )
            clocks = [
                build.calendar.clocks.final_available_ns,
                artifact.definition.adjustment.known_as_of_ns,
            ]
            for bar_identity in bars:
                if bar_identity is not None:
                    require(bar_identity in members, "target input not in frozen build")
                    bar = self.resolve(TargetBar, bar_identity)
                    require(
                        bar.instrument == artifact.origin.instrument,
                        "target cross-security price",
                    )
                    clocks.append(bar.clocks.final_available_ns)
            times = tuple(
                self.resolve(TargetBar, identity).period.end_ns
                for identity in artifact.path_ids
            )
            require(
                times == tuple(sorted(times)) and len(set(times)) == len(times),
                "unordered/conflicting target path",
            )
            require(
                len(times) <= self.target_bounds.path_observations,
                "path observation bound exceeded",
            )
            for identity in artifact.action_ids:
                require(
                    build.action_stream is not None
                    and identity in build.action_stream.action_ids,
                    "action not in frozen stream",
                )
                action = self.resolve(TargetCorporateAction, identity)
                require(
                    action.instrument == artifact.origin.instrument,
                    "target cross-security action",
                )
                clocks.append(action.clocks.final_available_ns)
            if artifact.definition.adjustment.source_dataset_id is not None:
                require(
                    build.action_stream is None
                    or build.action_stream.dataset_id
                    == artifact.definition.adjustment.source_dataset_id,
                    "target adjustment stream mismatch",
                )
                if build.action_stream is not None:
                    clocks.append(build.action_stream.clocks.final_available_ns)
            if artifact.benchmark_id is not None:
                require(
                    artifact.benchmark_id in build.benchmark_ids,
                    "benchmark outside frozen source build",
                )
                benchmark = self.resolve(SuppliedBenchmarkReturn, artifact.benchmark_id)
                require(
                    benchmark.benchmark == artifact.definition.benchmark
                    and benchmark.window == artifact.window,
                    "target benchmark definition/window mismatch",
                )
                clocks.append(benchmark.clocks.final_available_ns)
            require(
                artifact.clocks.final_available_ns >= max(clocks),
                "target backdated before input availability",
            )
            from afre.target_engine.builders import build_vintage

            universe = self.resolve(UniverseManifest, artifact.origin.universe_id)
            replay = build_vintage(
                self,
                artifact.definition,
                artifact.origin,
                build,
                artifact.clocks,
                universe.eligible(artifact.origin),
            )
            require(replay == artifact, "target deterministic calculation/evidence mismatch")
        elif isinstance(artifact, TargetDatasetManifest):
            build = self.resolve(TargetSourceBuild, artifact.source_build_id)
            self.resolve(TargetSetManifest, artifact.targets.fingerprint)
            self.resolve(UniverseManifest, artifact.universe.fingerprint)
            require(
                artifact.build_cutoff_ns == build.known_as_of_ns,
                "target dataset cutoff mismatch",
            )
            grid = set()
            for identity in artifact.row_ids:
                value = self.resolve(TargetVintage, identity)
                require(
                    value.source_build_id == artifact.source_build_id
                    and value.definition in artifact.targets.definitions
                    and value.origin in artifact.origins
                    and value.clocks.afre_computed_ns <= artifact.constructed_ns,
                    "target dataset row lineage mismatch",
                )
                grid.add((value.definition.fingerprint, value.origin.fingerprint))
            require(len(grid) == len(artifact.row_ids), "duplicate target dataset grid cell")
        elif isinstance(artifact, TargetAudit):
            self.resolve(TargetVintage, artifact.vintage.fingerprint)
            require(
                set(artifact.lineage_ids)
                == {item.fingerprint for item in self.lineage(artifact.vintage.fingerprint)},
                "target audit lineage mismatch",
            )

    def bars(
        self, build: TargetSourceBuild, instrument_id: str, start_ns: int, end_ns: int
    ) -> tuple[TargetBar, ...]:
        rows = self._connection.execute(
            (
                "SELECT bar_id FROM target_build_bars WHERE build_id = ? AND "
                "instrument_id = ? AND end_ns >= ? AND end_ns <= ? ORDER BY "
                "end_ns, bar_id LIMIT ?"
            ),
            (
                self.source_identity(build),
                instrument_id,
                start_ns,
                end_ns,
                self.target_bounds.path_observations + 1,
            ),
        ).fetchall()
        require(
            len(rows) <= self.target_bounds.path_observations,
            "path/candidate observation bound exceeded",
        )
        return tuple(self.resolve(TargetBar, row[0]) for row in rows)

    def lineage(self, identity: str) -> tuple[Artifact, ...]:
        if not identity.startswith("afre.target_"):
            return super().lineage(identity)
        seen: set[str] = set()
        active: set[str] = set()
        results: list[Artifact] = []
        size = 0

        def visit(current: str, depth: int) -> None:
            nonlocal size
            require(depth <= self.target_bounds.lineage_depth, "target lineage depth bound")
            require(current not in active, "target lineage cycle")
            if current in seen:
                return
            require(
                len(seen) + len(active) < self.target_bounds.lineage_nodes,
                "target lineage node bound",
            )
            active.add(current)
            value = self.get_any(current)
            edges: tuple[str, ...] = ()
            if isinstance(value, TargetVintage):
                edges = (
                    value.definition.fingerprint,
                    value.source_build_id,
                    *value.path_ids,
                    *value.action_ids,
                )
                edges += tuple(
                    item
                    for item in (value.origin_bar_id, value.endpoint_bar_id, value.benchmark_id)
                    if item is not None
                )
            elif isinstance(value, TargetSourceBuild):
                edges = (value.source.fingerprint, value.calendar.fingerprint)
                if value.action_stream is not None:
                    edges += (value.action_stream.fingerprint,)
            elif isinstance(value, TargetMarketSource):
                edges = (value.upstream.fingerprint,)
            elif isinstance(value, SourceReference):
                edges = value.parent_source_ids
            elif isinstance(value, TargetBar):
                edges = (value.source.fingerprint,)
                if value.predecessor_id is not None:
                    edges += (value.predecessor_id,)
            elif isinstance(value, TargetActionStream):
                edges = value.action_ids
            elif isinstance(value, (TargetCorporateAction, SuppliedBenchmarkReturn)):
                if value.predecessor_id is not None:
                    edges = (value.predecessor_id,)
                if isinstance(value, SuppliedBenchmarkReturn):
                    edges += (value.benchmark.fingerprint,)
            elif isinstance(value, TargetDefinition) and value.benchmark is not None:
                edges = (value.benchmark.fingerprint,)
            elif isinstance(value, TargetSetManifest):
                edges = tuple(item.fingerprint for item in value.definitions)
            elif isinstance(value, TargetDatasetManifest):
                edges = (
                    value.source_build_id,
                    value.targets.fingerprint,
                    value.universe.fingerprint,
                    *value.row_ids,
                )
            elif isinstance(value, TargetAudit):
                edges = (value.vintage.fingerprint,)
            for edge in sorted(set(edges)):
                visit(edge, depth + 1)
            active.remove(current)
            seen.add(current)
            size += len(canonical_json(value).encode())
            require(
                size <= self.target_bounds.serialized_bytes,
                "target lineage serialized byte bound",
            )
            results.append(value)

        visit(identity, 0)
        return tuple(results)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        with self.validation_cache():
            count = super().audit()
            classes = {cls.__name__: cls for cls in TARGET_TYPES}
            for identity, name in self._connection.execute(
                "SELECT fingerprint, type_name FROM target_artifacts"
            ):
                require(name in classes, "unknown target artifact family")
                value = self.get(classes[name], identity)
                self._validate_links(value)
                count += 1
            for table in (
                "target_definitions",
                "target_bars",
                "target_vintages",
                "target_datasets",
            ):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} LEFT JOIN target_artifacts "
                        f"ON {table}.fingerprint = target_artifacts.fingerprint "
                        "WHERE target_artifacts.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan target index",
                )
            for table, parent, member, member_table in (
                ("target_build_bars", "build_id", "bar_id", "target_bars"),
                ("target_dataset_rows", "dataset_id", "row_id", "target_vintages"),
            ):
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} LEFT JOIN target_artifacts p "
                        f"ON {table}.{parent} = p.fingerprint LEFT JOIN {member_table} m "
                        f"ON {table}.{member} = m.fingerprint "
                        "WHERE p.fingerprint IS NULL OR m.fingerprint IS NULL"
                    ).fetchone()[0]
                    == 0,
                    "orphan target membership index",
                )
        return count
