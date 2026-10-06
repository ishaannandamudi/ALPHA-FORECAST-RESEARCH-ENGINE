"""Additive store 1.15, exact immutable projections and preserved prior DDL/metadata."""

from afre.schema import Artifact
from afre.sequence.storage import METADATA as PREVIOUS_METADATA
from afre.sequence.storage import all_statements as previous_statements
from afre.uncertainty.artifacts import (
    ForecastUncertaintyDecomposition,
    ParameterCovariance,
    UncertaintyComponent,
    UncertaintyInterval,
)
from afre.uncertainty.definitions import ParameterUncertaintySpec, UncertaintySpec
from afre.uncertainty.evaluation_artifacts import UncertaintyEvaluation

METADATA = {
    **PREVIOUS_METADATA,
    "uncertainty_store_schema_version": "1.15",
    "uncertainty_schema": "1.0",
    "uncertainty_engine_version": "0.16.0",
}


def uncertainty_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE unc_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE unc_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "forecast_id TEXT, source_id TEXT, component TEXT, measure TEXT, status TEXT, "
            "target_id TEXT, horizon_id TEXT, security_id TEXT, origin_ns INTEGER, "
            "fold_id TEXT, spec_id TEXT, available_ns INTEGER, cutoff_ns INTEGER, test_id TEXT)"
        ),
        (
            "CREATE TABLE unc_links (fingerprint TEXT NOT NULL, reference_id TEXT NOT NULL, "
            "PRIMARY KEY (fingerprint, reference_id))"
        ),
        "CREATE INDEX unc_forecast_idx ON unc_records (forecast_id, source_id, available_ns)",
        (
            "CREATE INDEX unc_component_idx ON unc_records "
            "(component, measure, status, available_ns)"
        ),
        "CREATE INDEX unc_target_idx ON unc_records (target_id, horizon_id, available_ns)",
        "CREATE INDEX unc_origin_idx ON unc_records (security_id, origin_ns, available_ns)",
        "CREATE INDEX unc_evaluation_idx ON unc_records (fold_id, cutoff_ns, test_id)",
        "CREATE INDEX unc_reference_idx ON unc_links (reference_id, fingerprint)",
    ]
    for table in ("unc_artifacts", "unc_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} WHEN "
            f"EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
    for table in ("unc_artifacts", "unc_records", "unc_links"):
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE {operation} "
                f"ON {table} BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def all_statements() -> tuple[str, ...]:
    return (*previous_statements(), *uncertainty_schema())


def uncertainty_index(value: Artifact) -> tuple[object, ...]:
    forecast = source = component = measure = status = target = horizon = security = origin = (
        fold
    ) = spec = available = cutoff = test = None
    if isinstance(value, UncertaintySpec):
        forecast, target, horizon, spec = (
            value.forecast_id,
            value.target.fingerprint,
            value.target.horizon.fingerprint,
            value.fingerprint,
        )
    elif isinstance(value, ParameterUncertaintySpec):
        source, spec = value.model_id, value.fingerprint
    elif isinstance(value, ParameterCovariance):
        source, status, target, horizon, fold, spec, available, cutoff = (
            value.model_id,
            value.status.value,
            value.target_id,
            value.horizon_id,
            value.fold_id,
            value.spec_id,
            value.available_ns,
            value.cutoff_ns,
        )
    elif isinstance(value, UncertaintyComponent):
        component, measure, status, spec, available = (
            value.component.value,
            value.measure.value,
            value.status.value,
            value.spec_id,
            value.available_ns,
        )
        source = value.source_ids[0] if value.source_ids else None
    elif isinstance(value, UncertaintyInterval):
        forecast, spec, available, status = (
            value.forecast_id,
            value.spec_id,
            value.available_ns,
            value.status.value,
        )
    elif isinstance(value, ForecastUncertaintyDecomposition):
        forecast, target, horizon, security, origin, fold, spec, available = (
            value.forecast_id,
            value.target_id,
            value.horizon_id,
            value.origin.instrument.fingerprint,
            value.origin.timestamp_ns,
            value.fold_id,
            value.spec_id,
            value.available_ns,
        )
    elif isinstance(value, UncertaintyEvaluation):
        target, horizon, fold, spec, available, cutoff, test = (
            value.target_definition_id,
            value.horizon_id,
            value.fold_id,
            value.evaluation_spec_id,
            value.available_ns,
            value.cutoff_ns,
            value.test_evaluation_id,
        )
    return (
        value.fingerprint,
        forecast,
        source,
        component,
        measure,
        status,
        target,
        horizon,
        security,
        origin,
        fold,
        spec,
        available,
        cutoff,
        test,
    )
