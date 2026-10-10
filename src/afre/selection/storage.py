"""Additive SQLite21 selection tables and immutable searchable projections."""

from afre.multiple_testing.storage import METADATA as PREVIOUS_METADATA
from afre.multiple_testing.storage import all_statements as previous_statements
from afre.schema import Artifact

METADATA = {
    **PREVIOUS_METADATA,
    "selection_store_schema_version": "1.20",
    "selection_schema": "1.0",
    "selection_engine_version": "0.21.0",
}


def selection_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE sel_artifacts (fingerprint TEXT PRIMARY KEY NOT "
            "NULL, type_name TEXT NOT NULL, schema_version TEXT NOT NULL, "
            "payload TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE sel_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "kind TEXT NOT NULL, space_id TEXT, candidate_id TEXT, "
            "native_phase INTEGER, target_id TEXT, horizon_id TEXT, dataset_id "
            "TEXT, fold_id TEXT, criterion TEXT, cutoff_ns INTEGER, "
            "selected_id TEXT, family_id TEXT, trial_id TEXT)"
        ),
        (
            "CREATE TABLE sel_links (fingerprint TEXT NOT NULL, reference_id "
            "TEXT NOT NULL, PRIMARY KEY (fingerprint, reference_id))"
        ),
        "CREATE INDEX sel_space_idx ON sel_records (space_id, candidate_id)",
        "CREATE INDEX sel_family_idx ON sel_records (native_phase, family_id, trial_id)",
        (
            "CREATE INDEX sel_context_idx ON sel_records (target_id, "
            "horizon_id, dataset_id, fold_id)"
        ),
        "CREATE INDEX sel_criterion_idx ON sel_records (criterion, cutoff_ns, selected_id)",
        "CREATE INDEX sel_reference_idx ON sel_links (reference_id, fingerprint)",
    ]
    for table in ("sel_artifacts", "sel_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
    for table in ("sel_artifacts", "sel_records", "sel_links"):
        for op in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{op.lower()} BEFORE {op} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def all_statements() -> tuple[str, ...]:
    return (*previous_statements(), *selection_schema())


def record_index(v: Artifact) -> tuple[object, ...]:
    criterion = getattr(v, "criterion", None)
    recipe = getattr(v, "recipe", None)
    return (
        v.fingerprint,
        type(v).__name__,
        getattr(v, "search_space_id", None),
        getattr(v, "candidate_id", None),
        getattr(recipe, "native_phase", None),
        getattr(v, "target_id", None),
        getattr(v, "horizon_id", None),
        getattr(v, "dataset_id", None),
        getattr(v, "fold_id", None),
        getattr(criterion, "value", None),
        getattr(v, "truth_cutoff_ns", getattr(v, "selection_cutoff_ns", None)),
        getattr(v, "selected_candidate_id", None),
        getattr(v, "multiple_testing_family_id", None),
        getattr(v, "trial_id", None),
    )
