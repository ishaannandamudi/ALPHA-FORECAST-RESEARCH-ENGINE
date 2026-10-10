"""Immutable additive store21, guarded native reads and exact semantic replay."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ClassVar, TypeVar, cast

from afre.ids import validate_fingerprint
from afre.multiple_testing.repository import MultipleTestingRepository
from afre.research_datasets.definitions import ResearchDatasetDefinition
from afre.research_datasets.manifests import ResearchDatasetManifest, ResearchInputBuild
from afre.research_datasets.samples import ResearchSample, ResearchSelection
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import (
    FoldDefinition,
    FoldMembership,
    ResearchSplit,
    SplitDefinition,
)
from afre.schema import Artifact, require
from afre.selection.budgets import ResourceBudget, ResourceUsage
from afre.selection.comparisons import CandidateComparison
from afre.selection.definitions import (
    CandidateFamilyPlan,
    CandidateSpec,
    DiscreteDimension,
    NativeCandidateRecipe,
    SearchSpace,
    SelectionRequest,
)
from afre.selection.guards import guard_identity, guard_value
from afre.selection.lineage import SelectionAudit
from afre.selection.orthogonal_features import OrthogonalFeatureBinding
from afre.selection.registry import CandidateRegistryEntry, CandidateRegistrySnapshot
from afre.selection.results import (
    CandidateFitResult,
    CandidateValidationPair,
    CandidateValidationResult,
    SelectionResult,
)
from afre.selection.schema import SelectionBounds, SelectionReadRole
from afre.selection.storage import METADATA, all_statements, record_index, selection_schema
from afre.serialization import canonical_json, deserialize

SELECTION_TYPES: tuple[type[Artifact], ...] = (
    SelectionBounds,
    ResourceBudget,
    ResourceUsage,
    DiscreteDimension,
    NativeCandidateRecipe,
    SearchSpace,
    CandidateSpec,
    CandidateFamilyPlan,
    SelectionRequest,
    CandidateFitResult,
    CandidateValidationPair,
    CandidateValidationResult,
    SelectionResult,
    CandidateRegistryEntry,
    CandidateRegistrySnapshot,
    SelectionAudit,
    OrthogonalFeatureBinding,
    CandidateComparison,
)
A = TypeVar("A", bound=Artifact)


class SelectionRepository(MultipleTestingRepository):
    _snapshot_engine_version: ClassVar[str] = "0.21.0"

    def __init__(self, path: str | Path, bounds: SelectionBounds | None = None) -> None:
        self.selection_bounds = bounds or SelectionBounds()
        self._selection_role: SelectionReadRole | None = None
        self._selection_space: SearchSpace | None = None
        self._selection_targets: set[str] = set()
        self._selection_validating: set[str] = set()
        self._selection_validated: set[str] = set()
        super().__init__(path)

    @contextmanager
    def validation_cache(self) -> Iterator[None]:
        outer = self._validation_cache is None
        with super().validation_cache():
            try:
                yield
            finally:
                if outer:
                    self._selection_validated.clear()

    def _migrate(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        require(version in range(22), "unknown future selection store version")
        if version == 21:
            return
        if version < 20:
            MultipleTestingRepository._migrate(self)
        with self.transaction():
            MultipleTestingRepository._validate_layout(self)
            for sql in selection_schema():
                self._connection.execute(sql)
            self._connection.executemany(
                "INSERT INTO metadata VALUES (?,?)",
                (
                    ("selection_store_schema_version", "1.20"),
                    ("selection_schema", "1.0"),
                    ("selection_engine_version", "0.21.0"),
                ),
            )
            self._connection.execute("PRAGMA user_version=21")

    def _validate_layout(self) -> None:
        require(
            {
                s.split()[3] if s.startswith("CREATE UNIQUE INDEX") else s.split()[2]: s
                for s in all_statements()
            }
            == dict(
                self._connection.execute(
                    "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            ),
            "selection layout corruption",
        )
        require(
            dict(self._connection.execute("SELECT key,value FROM metadata")) == METADATA
            and self._connection.execute("PRAGMA user_version").fetchone()[0] == 21,
            "selection metadata/version corruption",
        )

    def get(self, cls: type[A], identity: str) -> A:
        guard_identity(self, cls, identity)
        if cls not in SELECTION_TYPES:
            value = super().get(cls, identity)
            guard_value(self, value)
            return value
        self._guard(cls)
        validate_fingerprint(identity, cls.domain)
        row = self._connection.execute(
            (
                "SELECT type_name,schema_version,CASE WHEN length(CAST(payload AS "
                "BLOB))<=? THEN payload ELSE NULL END FROM sel_artifacts WHERE "
                "fingerprint=?"
            ),
            (self.selection_bounds.payload_bytes, identity),
        ).fetchone()
        if row is None:
            raise KeyError(identity)
        require(
            row[:2] == (cls.__name__, "1.0") and type(row[2]) is str,
            "selection payload bounds/type/schema",
        )
        decoded = deserialize(row[2])
        self._selection_check_bounds(decoded)
        require(
            type(decoded) is cls and decoded.fingerprint == identity,
            "selection hash corruption",
        )
        require(
            self._connection.execute(
                "SELECT * FROM sel_records WHERE fingerprint=?", (identity,)
            ).fetchone()
            == record_index(decoded),
            "selection index corruption",
        )
        from afre.selection.lineage import selection_edges

        require(
            tuple(
                r[0]
                for r in self._connection.execute(
                    (
                        "SELECT reference_id FROM sel_links WHERE fingerprint=? ORDER BY "
                        "reference_id"
                    ),
                    (identity,),
                )
            )
            == tuple(sorted(set(selection_edges(decoded)))),
            "selection link corruption",
        )
        return cast(A, decoded)

    def resolve(self, cls: type[A], identity: str) -> A:
        guard_identity(self, cls, identity)
        if cls not in SELECTION_TYPES:
            value = super().resolve(cls, identity)
            guard_value(self, value)
            return value
        if self._validation_cache is None:
            if not self._reading and not self._in_transaction:
                with self.read_snapshot(), self.validation_cache():
                    return self.resolve(cls, identity)
            with self.validation_cache():
                return self.resolve(cls, identity)
        value = self.get(cls, identity)
        self._validate_links(value)
        return value

    def get_any(self, identity: str) -> Artifact:
        validate_fingerprint(identity)
        if self._validation_cache is not None and identity in self._validation_cache:
            guard_identity(self, type(self._validation_cache[identity]), identity)
            guard_value(self, self._validation_cache[identity])
        if not identity.startswith("afre.sel_"):
            value = super().get_any(identity)
            guard_value(self, value)
            return value
        row = self._connection.execute(
            "SELECT type_name FROM sel_artifacts WHERE fingerprint=?", (identity,)
        ).fetchone()
        classes = {c.__name__: c for c in SELECTION_TYPES}
        require(row is not None and row[0] in classes, "unresolved selection reference")
        assert row is not None
        return self.resolve(classes[row[0]], identity)

    def put(self, value: Artifact) -> str:
        if type(value) not in SELECTION_TYPES:
            return super().put(value)
        require(self._in_transaction, "selection write requires transaction")
        payload = canonical_json(value)
        self._selection_check_bounds(value)
        require(
            len(payload.encode()) <= self.selection_bounds.payload_bytes,
            "selection payload bound",
        )
        require(deserialize(payload) == value, "selection canonical mismatch")
        self._validate_links(value)
        if self._connection.execute(
            "SELECT 1 FROM sel_artifacts WHERE fingerprint=?", (value.fingerprint,)
        ).fetchone():
            require(
                self.get(type(value), value.fingerprint) == value,
                "conflicting selection payload",
            )
            return value.fingerprint
        require(
            self._connection.execute("SELECT count(*) FROM sel_artifacts").fetchone()[0]
            < self.selection_bounds.artifacts,
            "stored selection artifact bound",
        )
        self._connection.execute(
            "INSERT INTO sel_artifacts VALUES (?,?,?,?)",
            (value.fingerprint, type(value).__name__, "1.0", payload),
        )
        self._connection.execute(
            "INSERT INTO sel_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", record_index(value)
        )
        from afre.selection.lineage import selection_edges

        self._connection.executemany(
            "INSERT INTO sel_links VALUES (?,?)",
            tuple((value.fingerprint, i) for i in sorted(set(selection_edges(value)))),
        )
        return value.fingerprint

    def partition_samples(
        self, fold_id: str, partition: Partition
    ) -> tuple[ResearchSample, ...]:
        fold = self.get(FoldDefinition, fold_id)
        dataset = self.get(ResearchDatasetManifest, fold.dataset_id)
        definition = self.get(SplitDefinition, fold.split_definition_id)
        samples = tuple(self.get(ResearchSample, i) for i in dataset.sample_ids)
        rows = self._connection.execute(
            "SELECT fingerprint FROM r_memberships WHERE fold_id=? ORDER BY sample_id",
            (fold_id,),
        ).fetchall()
        require(len(rows) <= self.dataset_bounds.samples, "selection membership bound")
        memberships = tuple(self.get(FoldMembership, row[0]) for row in rows)
        from afre.research_datasets.splitting import folds_for
        from afre.selection.geometry import metadata_memberships_for

        folds = folds_for(fold.dataset_id, definition)
        require(
            fold in folds
            and set(memberships)
            == set(metadata_memberships_for(self, fold, definition, samples, folds)),
            "selection native split geometry replay",
        )
        chosen = {m.sample_id for m in memberships if m.partition is partition}
        return tuple(s for s in samples if s.fingerprint in chosen)

    def _validate_links(self, value: Artifact) -> None:
        if self._selection_role is not None and isinstance(
            value,
            (
                ResearchSelection,
                ResearchInputBuild,
                ResearchSample,
                ResearchDatasetManifest,
                ResearchDatasetDefinition,
                FoldDefinition,
                FoldMembership,
                ResearchSplit,
                SplitDefinition,
            ),
        ):
            from afre.selection.metadata import validate_metadata

            validate_metadata(self, value)
            # Closed metadata decoder and relational projections are checked by get.
            # TRAIN/VALIDATION recipe admission separately verifies native split geometry.
            # Rebuilding an entire dataset here would join held-out target values.
            return
        if type(value) not in SELECTION_TYPES:
            super()._validate_links(value)
            return
        if value.fingerprint in self._selection_validated:
            return
        require(
            value.fingerprint not in self._selection_validating, "selection reference cycle"
        )
        self._selection_validating.add(value.fingerprint)
        try:
            from afre.selection.validation import validate_selection

            validate_selection(self, value)
            self._selection_validated.add(value.fingerprint)
        finally:
            self._selection_validating.remove(value.fingerprint)

    def _selection_check_bounds(self, value: Artifact) -> None:
        b = self.selection_bounds
        for field, maximum in (
            ("candidate_ids", b.candidates),
            ("entries", b.candidates),
            ("forecast_ids", b.rows),
            ("pairs", b.rows),
            ("declared_sample_ids", b.rows),
        ):
            require(
                len(getattr(value, field, ())) <= maximum, "configured selection artifact bound"
            )
        if isinstance(value, CandidateComparison):
            existing = self._connection.execute(
                "SELECT 1 FROM sel_artifacts WHERE fingerprint=?", (value.fingerprint,)
            ).fetchone()
            require(
                existing is not None
                or self._connection.execute(
                    "SELECT count(*) FROM sel_artifacts WHERE type_name='CandidateComparison'"
                ).fetchone()[0]
                < b.comparisons,
                "stored comparison bound",
            )

    def audit(self) -> int:
        if not self._reading and not self._in_transaction:
            with self.read_snapshot(), self.validation_cache():
                return self.audit()
        count = super().audit()
        for (identity,) in self._connection.execute(
            "SELECT fingerprint FROM sel_artifacts ORDER BY fingerprint"
        ):
            self.get_any(identity)
            count += 1
        for table in ("sel_records", "sel_links"):
            require(
                self._connection.execute(
                    f"SELECT count(*) FROM {table} r LEFT JOIN sel_artifacts a "
                    "ON r.fingerprint=a.fingerprint WHERE a.fingerprint IS NULL"
                ).fetchone()[0]
                == 0,
                "orphan selection projection",
            )
        return count
