"""Additive immutable event registry with verified relational projections."""

from afre.event_conditioned.artifacts import (
    EventCalibrationAssessment,
    EventConditionedEvaluation,
    EventConditionedForecast,
    EventConditionedModel,
    EventConditionedObservation,
    EventMatchSet,
)
from afre.event_conditioned.definitions import EventConditioningSpec
from afre.event_conditioned.events import EventReference
from afre.schema import Artifact


def event_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE ec_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE ec_records (fingerprint TEXT PRIMARY KEY NOT NULL, event_id TEXT, "
            "event_class TEXT, security_id TEXT, scope TEXT, available_ns INTEGER, "
            "origin_ns INTEGER, "
            "target_id TEXT, horizon_id TEXT, spec_id TEXT, base_model_id TEXT, model_id TEXT, "
            "cutoff_ns INTEGER, test_id TEXT)"
        ),
        "CREATE INDEX ec_event_idx ON ec_records (event_id, available_ns)",
        (
            "CREATE INDEX ec_class_idx ON ec_records "
            "(event_class, scope, security_id, available_ns)"
        ),
        "CREATE INDEX ec_origin_idx ON ec_records (origin_ns, target_id, horizon_id)",
        "CREATE INDEX ec_model_idx ON ec_records (spec_id, base_model_id, model_id, cutoff_ns)",
        "CREATE INDEX ec_test_idx ON ec_records (test_id, cutoff_ns)",
    ]
    for table in ("ec_artifacts", "ec_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} WHEN "
            f"EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
        for op in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{op.lower()} BEFORE {op} ON {table} "
                "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def event_index(value: Artifact) -> tuple[object, ...]:
    event = cls = security = scope = available = origin = target = horizon = spec = base = (
        model
    ) = cutoff = test = None
    if isinstance(value, EventReference):
        event, cls, scope, available = (
            value.event_id,
            value.event_class.value,
            value.subject.scope.value,
            value.clocks.final_available_ns,
        )
        security = (
            value.subject.security.fingerprint
            if value.subject.security
            else value.subject.issuer.fingerprint
            if value.subject.issuer
            else value.subject.group_id
        )
    elif isinstance(value, EventConditioningSpec):
        spec, base, target, horizon = (
            value.fingerprint,
            value.base_model_id,
            value.window.target.fingerprint,
            value.window.target.horizon.fingerprint,
        )
    elif isinstance(value, EventMatchSet):
        spec = value.spec_id
    elif isinstance(value, EventConditionedObservation):
        spec, security, origin, event = (
            value.spec_id,
            value.security.fingerprint,
            value.origin.timestamp_ns,
            value.event_id,
        )
    elif isinstance(value, EventConditionedModel):
        model, spec, cutoff, available = (
            value.fingerprint,
            value.spec_id,
            value.cutoff_ns,
            value.available_ns,
        )
    elif isinstance(value, EventConditionedForecast):
        model, spec, security, origin, available, target = (
            value.model_id,
            value.spec_id,
            value.security.fingerprint,
            value.origin.timestamp_ns,
            value.available_ns,
            value.target_definition_id,
        )
    elif isinstance(value, EventConditionedEvaluation):
        model, cutoff, available, test = (
            value.model_id,
            value.cutoff_ns,
            value.available_ns,
            value.test_evaluation_id,
        )
    elif isinstance(value, EventCalibrationAssessment):
        cutoff = value.cutoff_ns
    return (
        value.fingerprint,
        event,
        cls,
        security,
        scope,
        available,
        origin,
        target,
        horizon,
        spec,
        base,
        model,
        cutoff,
        test,
    )
