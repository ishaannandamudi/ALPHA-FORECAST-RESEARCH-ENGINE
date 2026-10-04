"""Fixed additive DDL and independently checked relational indexes."""

from afre.research_datasets.manifests import ResearchDatasetManifest
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.splits import FoldDefinition, FoldMembership, ResearchSplit
from afre.schema import Artifact

TABLES = (
    "r_artifacts",
    "r_samples",
    "r_dataset_samples",
    "r_folds",
    "r_memberships",
    "r_split_folds",
)


def dataset_schema() -> tuple[str, ...]:
    statements = [
        "CREATE TABLE r_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT "
        "NOT NULL)",
        "CREATE TABLE r_samples (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "build_id TEXT NOT NULL, security_id TEXT NOT NULL, origin_ns INTEGER "
        "NOT NULL, target_definition_id TEXT NOT NULL, target_start_ns "
        "INTEGER, target_end_ns INTEGER, target_available_ns INTEGER, state "
        "TEXT NOT NULL)",
        "CREATE TABLE r_dataset_samples (fingerprint TEXT PRIMARY KEY NOT "
        "NULL, dataset_id TEXT NOT NULL, sample_id TEXT NOT NULL, ordinal "
        "INTEGER NOT NULL, UNIQUE(dataset_id, sample_id), UNIQUE(dataset_id, "
        "ordinal))",
        "CREATE TABLE r_folds (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "dataset_id TEXT NOT NULL, definition_id TEXT NOT NULL, ordinal "
        "INTEGER NOT NULL, cutoff_ns INTEGER NOT NULL, UNIQUE(dataset_id, "
        "definition_id, ordinal))",
        "CREATE TABLE r_memberships (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "fold_id TEXT NOT NULL, sample_id TEXT NOT NULL, partition TEXT NOT "
        "NULL, UNIQUE(fold_id, sample_id))",
        "CREATE TABLE r_split_folds (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "split_id TEXT NOT NULL, fold_id TEXT NOT NULL, ordinal INTEGER NOT "
        "NULL, UNIQUE(split_id, fold_id), UNIQUE(split_id, ordinal))",
        "CREATE INDEX r_origin_idx ON r_samples (build_id, origin_ns, "
        "security_id, target_definition_id)",
        "CREATE INDEX r_interval_idx ON r_samples (target_start_ns, "
        "target_end_ns, security_id)",
        "CREATE INDEX r_available_idx ON r_samples (target_available_ns)",
        "CREATE INDEX r_dataset_idx ON r_dataset_samples (dataset_id, ordinal)",
        "CREATE INDEX r_partition_idx ON r_memberships (fold_id, partition, sample_id)",
        "CREATE INDEX r_split_idx ON r_folds (dataset_id, definition_id, ordinal)",
    ]
    for table in TABLES:
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} WHEN "
            f"EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) "
            f"BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE "
                f"{operation} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable AFRE "
                f"artifact'); END"
            )
    return tuple(statements)


def indexes(value: Artifact, identity: str) -> tuple[tuple[str, tuple[object, ...]], ...]:
    if isinstance(value, ResearchSample):
        interval = value.target_interval
        return (
            (
                "r_samples",
                (
                    identity,
                    value.input_build_id,
                    value.security.instrument.fingerprint,
                    value.timestamp_ns,
                    value.target_definition_id,
                    interval.start_ns if interval else None,
                    interval.end_ns if interval else None,
                    value.target_available_ns,
                    value.state.value,
                ),
            ),
        )
    if isinstance(value, FoldDefinition):
        return (
            (
                "r_folds",
                (
                    identity,
                    value.dataset_id,
                    value.split_definition_id,
                    value.ordinal,
                    value.training_cutoff_ns,
                ),
            ),
        )
    if isinstance(value, FoldMembership):
        return (
            (
                "r_memberships",
                (identity, value.fold_id, value.sample_id, value.partition.value),
            ),
        )
    if isinstance(value, ResearchDatasetManifest):
        return tuple(
            ("r_dataset_samples", (identity + "|" + sample, identity, sample, ordinal))
            for ordinal, sample in enumerate(value.sample_ids)
        )
    if isinstance(value, ResearchSplit):
        return tuple(
            ("r_split_folds", (identity + "|" + fold, identity, fold, ordinal))
            for ordinal, fold in enumerate(value.fold_ids)
        )
    return ()
