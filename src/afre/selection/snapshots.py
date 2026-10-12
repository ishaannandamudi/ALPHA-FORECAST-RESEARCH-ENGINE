"""Bounded isolated SQLite snapshot, then atomic immutable-row publication."""

from collections.abc import Callable

from afre.schema import require
from afre.selection.repository import SelectionRepository
from afre.selection.storage import all_statements

# Names originate exclusively in native static DDL, never a provider/search payload.
TABLES = tuple(
    s.split()[2]
    for s in all_statements()
    if s.startswith("CREATE TABLE") and s.split()[2] != "metadata"
)


def frozen_copy(
    repo: SelectionRepository, hook: Callable[[], None] | None
) -> SelectionRepository:
    # Later phases add strict immutable tables: preserve the concrete native layout.
    stage = type(repo)(":memory:")
    for name, value in vars(repo).items():
        if name == "bounds" or name.endswith("_bounds"):
            setattr(stage, name, value)
    try:
        with repo.read_snapshot():
            repo._connection.execute("SELECT count(*) FROM metadata").fetchone()
            pages = repo._connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = repo._connection.execute("PRAGMA page_size").fetchone()[0]
            require(
                pages * page_size <= repo.selection_bounds.snapshot_bytes,
                "selection snapshot byte bound",
            )
            # Copy database pages without logically loading TEST artifacts. Native
            # guards cover all decoded response access in the isolated repository.
            repo._connection.backup(stage._connection)
            if hook:
                hook()
        stage._validate_layout()
        return stage
    except BaseException:
        stage.close()
        raise


def publication_delta(
    repo: SelectionRepository, stage: SelectionRepository
) -> tuple[tuple[str, tuple[tuple[object, ...], ...]], ...]:
    result = []
    total = 0
    for table in TABLES:
        columns = tuple(stage._connection.execute(f"PRAGMA table_info({table})"))
        keys = tuple(i for i, c in enumerate(columns) if c[5])
        require(bool(keys), "native publication table requires immutable primary key")
        existing = {
            tuple(row[i] for i in keys): row
            for row in repo._connection.execute(f"SELECT * FROM {table}")
        }
        rows = []
        for row in stage._connection.execute(f"SELECT * FROM {table}"):
            old = existing.get(tuple(row[i] for i in keys))
            if old is None:
                total += 1
                require(
                    total <= repo.selection_bounds.publication_rows,
                    "selection publication row bound",
                )
                rows.append(row)
            else:
                require(old == row, "selection publication conflicting immutable row")
        result.append((table, tuple(rows)))
    return tuple(result)


def publish_stage(repo: SelectionRepository, stage: SelectionRepository) -> None:
    require(repo.selection_bounds == stage.selection_bounds, "same publication bounds")
    stage._validate_layout()
    from afre.selection.registry import CandidateRegistrySnapshot

    with stage.read_snapshot(), stage.validation_cache():
        for (identity,) in stage._connection.execute(
            "SELECT fingerprint FROM sel_artifacts WHERE type_name='CandidateRegistrySnapshot'"
        ):
            stage.resolve(CandidateRegistrySnapshot, identity)
    with repo.transaction():
        for table, rows in publication_delta(repo, stage):
            if rows:
                placeholders = ",".join("?" for _ in rows[0])
                repo._connection.executemany(
                    f"INSERT INTO {table} VALUES ({placeholders})", rows
                )
