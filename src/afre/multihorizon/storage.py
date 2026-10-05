"""Small additive tables; all index projections are checked on every read."""

from afre.multihorizon.artifacts import (
    CovarianceArtifact,
    MultiHorizonEvaluation,
    MultiHorizonFitRun,
    MultiHorizonForecast,
)
from afre.multihorizon.definitions import MultiHorizonModelSpec
from afre.multihorizon.horizon_sets import HorizonSet
from afre.schema import Artifact

TABLE_FAMILIES = (("mh_records", None),)


def multihorizon_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE mh_artifacts (fingerprint TEXT PRIMARY KEY NOT "
            "NULL, type_name TEXT NOT NULL, schema_version TEXT NOT "
            "NULL, payload TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE mh_records (fingerprint TEXT PRIMARY KEY NOT "
            "NULL, horizon_set_id TEXT, architecture TEXT, model_id "
            "TEXT, security_id TEXT, origin_ns INTEGER, cutoff_ns "
            "INTEGER, available_ns INTEGER, covariance_id TEXT)"
        ),
        (
            "CREATE TABLE mh_targets (fingerprint TEXT NOT NULL, "
            "target_id TEXT NOT NULL, horizon_id TEXT NOT NULL, model_id "
            "TEXT, fold_id TEXT, cutoff_ns INTEGER, PRIMARY KEY "
            "(fingerprint, target_id))"
        ),
        "CREATE INDEX mh_set_idx ON mh_records (horizon_set_id, architecture, fingerprint)",
        "CREATE INDEX mh_origin_idx ON mh_records (security_id, origin_ns, available_ns)",
        "CREATE INDEX mh_fit_idx ON mh_records (model_id, cutoff_ns, available_ns)",
        "CREATE INDEX mh_cov_idx ON mh_records (covariance_id, cutoff_ns)",
        (
            "CREATE INDEX mh_target_idx ON mh_targets (target_id, "
            "horizon_id, model_id, fold_id, cutoff_ns)"
        ),
    ]
    for table in ("mh_artifacts", "mh_records", "mh_targets"):
        key = "fingerprint=NEW.fingerprint" + (
            " AND target_id=NEW.target_id" if table == "mh_targets" else ""
        )
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE {key}) BEGIN SELECT RAISE(ABORT, "
            "'immutable AFRE artifact'); END"
        )
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE "
                f"{operation} ON {table} BEGIN SELECT RAISE(ABORT, "
                "'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def multihorizon_indexes(
    value: Artifact, identity: str
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    set_id = architecture = model_id = security_id = covariance_id = None
    origin = cutoff = available = None
    targets: list[tuple[object, ...]] = []
    if isinstance(value, HorizonSet):
        set_id = identity
        targets = [
            (identity, t.fingerprint, t.horizon.fingerprint, None, None, None)
            for t in value.targets
        ]
    elif isinstance(value, MultiHorizonModelSpec):
        set_id, architecture = value.horizon_set.fingerprint, value.architecture.value
        targets = [
            (
                identity,
                t.fingerprint,
                t.horizon.fingerprint,
                b.point_model_id,
                b.fold_id,
                b.training_cutoff_ns,
            )
            for t, b in zip(value.horizon_set.targets, value.bindings, strict=True)
        ]
    elif isinstance(value, MultiHorizonFitRun):
        model_id, cutoff, available = (
            value.spec_id,
            max(t.cutoff_ns for t in value.train),
            value.available_ns,
        )
    elif isinstance(value, CovarianceArtifact):
        model_id, cutoff, available, covariance_id = (
            value.fit_run_id,
            value.cutoff_ns,
            value.available_ns,
            identity,
        )
    elif isinstance(value, MultiHorizonForecast):
        set_id, architecture, model_id = (
            value.horizon_set_id,
            value.architecture.value,
            value.fit_run_id,
        )
        security_id, origin, available = (
            value.origin.instrument.fingerprint,
            value.origin.timestamp_ns,
            value.available_ns,
        )
        covariance_id = value.covariance_id
    elif isinstance(value, MultiHorizonEvaluation):
        model_id, cutoff, available = value.fit_run_id, value.cutoff_ns, value.available_ns
    return (
        (
            "mh_records",
            (
                identity,
                set_id,
                architecture,
                model_id,
                security_id,
                origin,
                cutoff,
                available,
                covariance_id,
            ),
        ),
        *(("mh_targets", row) for row in sorted(targets)),
    )
