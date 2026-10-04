"""Store 1.4: immutable research artifacts, indexes and snapshot-scoped validation."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar, cast

from afre.datasets import UniverseManifest
from afre.feature_store.repository import feature_store_schema
from afre.ids import validate_fingerprint
from afre.persistence import _schema_statements
from afre.research_datasets.audits import ContaminationAudit, SampleContaminationAudit
from afre.research_datasets.definitions import (
    DatasetCompatibility,
    ResearchDatasetDefinition,
    ResearchGroupBinding,
    ResearchOriginRequest,
)
from afre.research_datasets.intervals import SampleInformationInterval
from afre.research_datasets.manifests import (
    DatasetColumn,
    DatasetColumnManifest,
    ResearchDatasetManifest,
    ResearchInputBuild,
)
from afre.research_datasets.preprocessing import FoldPreprocessingSpec, FoldPreprocessingState
from afre.research_datasets.samples import ResearchSample, ResearchSelection
from afre.research_datasets.schema import DatasetBounds, Partition, PurgeScope
from afre.research_datasets.splits import (
    EmbargoBarGrid,
    EmbargoPolicy,
    FoldDefinition,
    FoldMembership,
    PurgePolicy,
    ResearchSplit,
    SplitDefinition,
    TestEvaluation,
)
from afre.research_datasets.storage import TABLES, dataset_schema, indexes
from afre.schema import Artifact, require
from afre.serialization import canonical_json, deserialize
from afre.target_engine.models import TargetVintage
from afre.target_engine.repository import target_schema
from afre.universe.identity import StableSecurityId
from afre.universe.models import EligibilityResult, UniverseSnapshot
from afre.universe.repository import UniverseRepository, universe_schema
from afre.universe.schema import UniverseBounds
from afre.universe.securities import SecurityRecord

RESEARCH_TYPES: tuple[type[Artifact], ...] = (
    DatasetBounds,
    DatasetCompatibility,
    ResearchGroupBinding,
    ResearchDatasetDefinition,
    ResearchOriginRequest,
    SampleInformationInterval,
    ResearchSelection,
    ResearchSample,
    DatasetColumn,
    DatasetColumnManifest,
    ResearchInputBuild,
    ResearchDatasetManifest,
    EmbargoBarGrid,
    EmbargoPolicy,
    PurgePolicy,
    SplitDefinition,
    FoldDefinition,
    FoldMembership,
    ResearchSplit,
    FoldPreprocessingSpec,
    FoldPreprocessingState,
    ContaminationAudit,
    SampleContaminationAudit,
    TestEvaluation,
)
R = TypeVar("R", bound=Artifact)


class DatasetRepository(UniverseRepository):
    def __init__(self, path: str | Path, bounds: DatasetBounds | None = None) -> None:
        self.dataset_bounds = bounds or DatasetBounds()
        self._reuse_read = False
        self._research_rows: dict[str, dict[tuple[str, str], TargetVintage]] = {}
        self._research_sets: dict[str, set[str]] = {}
        self._validated_upstream: set[str] = set()
        self._validated_folds: set[str] = set()
        self._feature_starts: dict[str, int] = {}
        self._research_projections: dict[str, UniverseManifest] = {}
        self._research_eligibility: dict[str, dict[StableSecurityId, EligibilityResult]] = {}
        self.last_interval_comparisons = 0
        super().__init__(
            path,
            UniverseBounds(
                securities=self.dataset_bounds.securities,
                serialized_bytes=self.dataset_bounds.serialized_bytes,
                lineage_nodes=self.dataset_bounds.audit_nodes,
                lineage_depth=self.dataset_bounds.lineage_depth,
            ),
        )

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        with super().validation_cache():
            try:
                yield
            finally:
                self._research_rows.clear()
                self._research_sets.clear()
                self._validated_upstream.clear()
                self._validated_folds.clear()
                self._feature_starts.clear()
                self._research_projections.clear()
                self._research_eligibility.clear()

    @contextmanager
    def _upstream_join_snapshot(self) -> Iterator[None]:
        require(self._reading and not self._reuse_read, "upstream join requires outer snapshot")
        self._reuse_read = True
        try:
            yield
        finally:
            self._reuse_read = False

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        if self._reuse_read and self._reading:
            yield
        else:
            with super().read_snapshot():
                yield

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in (0, 1, 2, 3, 4, 5), "unknown future research store version")
        if version == 5:
            return
        if version < 4:
            UniverseRepository._migrate(self)
        with self.transaction():
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 5:
                return
            require(version == 4, "unexpected research migration version")
            UniverseRepository._validate_layout(self)
            for statement in dataset_schema():
                self._connection.execute(statement)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?, ?)",
                (
                    ("research_store_schema_version", "1.4"),
                    ("dataset_schema", "1.0"),
                    ("research_engine_version", "0.5.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version = 5")

    def _validate_layout(self) -> None:
        expected = {
            s.split()[2]: s
            for s in (
                *_schema_statements(),
                *feature_store_schema(),
                *target_schema(),
                *universe_schema(),
                *dataset_schema(),
            )
        }
        actual = dict(
            self._connection.execute(
                "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
            )
        )
        require(expected == actual, "research schema/index/trigger corruption")
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
                "research_store_schema_version": "1.4",
                "dataset_schema": "1.0",
                "research_engine_version": "0.5.0",
            },
            "research metadata corruption",
        )
        require(
            self._connection.execute("PRAGMA user_version").fetchone()[0] == 5,
            "research integer version corruption",
        )

    def _check_bounds(self, value: Artifact) -> None:
        bounds = self.dataset_bounds
        if isinstance(value, ResearchDatasetDefinition):
            require(
                len(value.feature_set.definitions) <= bounds.features
                and len(value.target_set.definitions) <= bounds.targets,
                "research feature/target bound",
            )
        if isinstance(value, ResearchInputBuild):
            require(len(value.selection_ids) <= bounds.samples, "research selection bound")
        if isinstance(value, ResearchDatasetManifest):
            require(len(value.sample_ids) <= bounds.samples, "research sample bound")
        if isinstance(value, (ResearchSplit, SplitDefinition)):
            count = (
                len(value.fold_ids) if isinstance(value, ResearchSplit) else value.fold_count
            )
            require(count <= bounds.folds, "research fold bound")
        if isinstance(value, SampleContaminationAudit):
            require(len(value.evidence_ids) <= bounds.audit_nodes, "sample audit node bound")
        if isinstance(value, ContaminationAudit):
            require(
                len(value.lineage_ids) + len(value.exclusion_ids) <= bounds.audit_nodes,
                "research audit node bound",
            )

    def put(self, value: Artifact) -> str:
        if type(value) not in RESEARCH_TYPES:
            return super().put(value)
        require(
            self._in_transaction and not self._reading,
            "research writes require writer transaction",
        )
        payload = canonical_json(value)
        require(
            len(payload.encode()) <= self.dataset_bounds.serialized_bytes,
            "research serialized byte bound",
        )
        require(deserialize(payload) == value, "research canonical validation mismatch")
        self._check_bounds(value)
        identity = value.fingerprint
        if self._connection.execute(
            "SELECT 1 FROM r_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone():
            require(self.get(type(value), identity) == value, "research conflicting payload")
            return identity
        self._validate_links(value)
        self._connection.execute(
            "INSERT INTO r_artifacts VALUES (?, ?, ?, ?)",
            (identity, type(value).__name__, "1.0", payload),
        )
        for table, values in indexes(value, identity):
            self._connection.execute(
                f"INSERT INTO {table} VALUES ({','.join('?' for _ in values)})", values
            )
        return identity

    def get(self, cls: type[R], identity: str) -> R:
        if cls not in RESEARCH_TYPES:
            return super().get(cls, identity)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            "SELECT type_name,schema_version,payload FROM r_artifacts WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(row[:2] == (cls.__name__, "1.0"), "research family/schema corruption")
        require(
            len(row[2].encode()) <= self.dataset_bounds.serialized_bytes,
            "research serialized byte bound",
        )
        value = deserialize(row[2])
        require(
            type(value) is cls and value.fingerprint == identity,
            "research payload/fingerprint corruption",
        )
        self._check_bounds(value)
        for table, values in indexes(value, identity):
            require(
                self._connection.execute(
                    f"SELECT * FROM {table} WHERE fingerprint=?", (values[0],)
                ).fetchone()
                == values,
                "research relational index corruption",
            )
        for table, parent, count in (
            (
                "r_dataset_samples",
                "dataset_id",
                len(value.sample_ids) if isinstance(value, ResearchDatasetManifest) else -1,
            ),
            (
                "r_split_folds",
                "split_id",
                len(value.fold_ids) if isinstance(value, ResearchSplit) else -1,
            ),
        ):
            if count >= 0:
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} WHERE {parent}=?", (identity,)
                    ).fetchone()[0]
                    == count,
                    "research extra membership index",
                )
        return cast(R, value)

    def get_any(self, identity: str) -> Artifact:
        if not identity.startswith("afre.r_"):
            return super().get_any(identity)
        row = self._connection.execute(
            "SELECT type_name FROM r_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {cls.__name__: cls for cls in RESEARCH_TYPES}
        require(row is not None and row[0] in classes, "unresolved research reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def group_keys(
        self,
        definition: ResearchDatasetDefinition,
        security: object,
        at_ns: int,
        cutoff_ns: int,
        eligibility: EligibilityResult,
    ) -> tuple[tuple[str, str], ...]:
        groups: dict[str, str] = {}
        # Issuer follows exact security-master evidence used by the snapshot.
        for identity in eligibility.record_ids:
            record = self.get_any(identity)
            if isinstance(record, SecurityRecord):
                groups[PurgeScope.ISSUER.value] = record.issuer.instrument.fingerprint
        for binding in definition.group_bindings:
            if (
                binding.security == security
                and binding.validity.contains(at_ns)
                and binding.known_ns <= cutoff_ns
            ):
                old = groups.get(binding.scope.value)
                require(
                    old is None or old == binding.group,
                    "conflicting point-in-time group binding",
                )
                groups[binding.scope.value] = binding.group
        return tuple(sorted(groups.items()))

    def projection(self, snapshot: UniverseSnapshot) -> UniverseManifest:
        from afre.universe.validation import to_universe_manifest

        identity = self.identity(snapshot)
        if identity not in self._research_projections:
            self._research_projections[identity] = to_universe_manifest(snapshot)
        return self._research_projections[identity]

    def snapshot_eligibility(
        self, snapshot: UniverseSnapshot
    ) -> dict[StableSecurityId, EligibilityResult]:
        identity = self.identity(snapshot)
        if identity not in self._research_eligibility:
            self._research_eligibility[identity] = {
                x.membership.security: x for x in snapshot.eligibility
            }
        return self._research_eligibility[identity]

    def member_ids(self, identity: str, values: tuple[str, ...]) -> set[str]:
        if identity not in self._research_sets:
            self._research_sets[identity] = set(values)
        return self._research_sets[identity]

    def validate_upstream(self, value: Artifact) -> None:
        identity = self.identity(value)
        if identity not in self._validated_upstream:
            self._validate_links(value)
            self._validated_upstream.add(identity)

    def dataset_samples(self, dataset_id: str) -> tuple[ResearchSample, ...]:
        dataset = self.resolve(ResearchDatasetManifest, dataset_id)
        return tuple(self.resolve(ResearchSample, identity) for identity in dataset.sample_ids)

    def partition_samples(
        self, fold_id: str, partition: Partition
    ) -> tuple[ResearchSample, ...]:
        fold = self.resolve(FoldDefinition, fold_id)
        samples = self.dataset_samples(fold.dataset_id)
        memberships = self.fold_memberships(fold_id)
        require(
            {m.sample_id for m in memberships} == {self.identity(s) for s in samples},
            "incomplete fold membership grid",
        )
        if fold_id not in self._validated_folds:
            from afre.research_datasets.splitting import folds_for, memberships_for

            self._validate_links(fold)
            definition = self.resolve(SplitDefinition, fold.split_definition_id)
            expected = memberships_for(
                self, fold, definition, samples, folds_for(fold.dataset_id, definition)
            )
            require(set(memberships) == set(expected), "fold query contamination")
            self._validated_folds.add(fold_id)
        selected = {m.sample_id for m in memberships if m.partition is partition}
        return tuple(s for s in samples if self.identity(s) in selected)

    def fold_memberships(self, fold_id: str) -> tuple[FoldMembership, ...]:
        rows = self._connection.execute(
            "SELECT fingerprint FROM r_memberships WHERE fold_id=? ORDER BY sample_id",
            (fold_id,),
        ).fetchall()
        require(len(rows) <= self.dataset_bounds.samples, "membership sample bound")
        return tuple(self.resolve(FoldMembership, row[0]) for row in rows)

    def _validate_links(self, value: Artifact) -> None:
        if type(value) not in RESEARCH_TYPES:
            super()._validate_links(value)
            return
        from afre.research_datasets.validation import validate_links

        validate_links(self, value)

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot():
                return self.audit()
        count = super().audit()
        with self.validation_cache():
            classes = {cls.__name__: cls for cls in RESEARCH_TYPES}
            for identity, name in self._connection.execute(
                "SELECT fingerprint,type_name FROM r_artifacts"
            ):
                require(name in classes, "unknown research family")
                self._validate_links(self.resolve(classes[name], identity))
                count += 1
            for table in TABLES[1:]:
                expected_type = {
                    "r_samples": "ResearchSample",
                    "r_dataset_samples": "ResearchDatasetManifest",
                    "r_folds": "FoldDefinition",
                    "r_memberships": "FoldMembership",
                    "r_split_folds": "ResearchSplit",
                }[table]
                parent = {"r_dataset_samples": "dataset_id", "r_split_folds": "split_id"}.get(
                    table, "fingerprint"
                )
                require(
                    self._connection.execute(
                        f"SELECT count(*) FROM {table} LEFT JOIN r_artifacts a ON "
                        f"{table}.{parent}=a.fingerprint WHERE a.fingerprint IS NULL "
                        "OR a.type_name!=?",
                        (expected_type,),
                    ).fetchone()[0]
                    == 0,
                    "orphan research index",
                )
        return count
