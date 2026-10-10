"""Bounded data-only isolated planning and atomic publication of native trial rows."""

from afre.fusion.repository import FusionRepository
from afre.fusion.storage import all_statements
from afre.schema import require

TABLES = tuple(
    s.split()[2]
    for s in all_statements()
    if s.startswith("CREATE TABLE") and s.split()[2] != "metadata"
)


def frozen_copy(repo: FusionRepository) -> FusionRepository:
    stage = FusionRepository(":memory:", repo.fusion_bounds)
    try:
        with repo.read_snapshot():
            repo._connection.backup(stage._connection)
        stage._validate_layout()
        return stage
    except BaseException:
        stage.close()
        raise


def publish_stage(repo: FusionRepository, stage: FusionRepository) -> None:
    require(repo.fusion_bounds == stage.fusion_bounds, "same fusion publication bounds")
    stage._validate_layout()
    with repo.transaction():
        total = 0
        for table in TABLES:
            keys = tuple(
                i
                for i, c in enumerate(stage._connection.execute(f"PRAGMA table_info({table})"))
                if c[5]
            )
            require(bool(keys), "immutable fusion publication primary key")
            existing = {
                tuple(r[i] for i in keys): r
                for r in repo._connection.execute(f"SELECT * FROM {table}")
            }
            new = []
            for row in stage._connection.execute(f"SELECT * FROM {table}"):
                old = existing.get(tuple(row[i] for i in keys))
                if old is None:
                    total += 1
                    require(
                        total <= repo.fusion_bounds.publication_rows,
                        "fusion publication row bound",
                    )
                    new.append(row)
                else:
                    require(old == row, "fusion publication conflicting immutable content")
            if new:
                placeholders = ",".join("?" for _ in new[0])
                repo._connection.executemany(
                    f"INSERT INTO {table} VALUES ({placeholders})", new
                )
