"""Additive data-only tables with immutable independently verified research projections."""

from afre.nonlinear.artifacts import (
    FittedTransformArtifact,
    InteractionMatrix,
    InteractionValue,
    NonlinearEvaluation,
    NonlinearForecast,
    NonlinearModelArtifact,
    ScalarInput,
)
from afre.nonlinear.definitions import InteractionDefinition, InteractionSet, NonlinearModelSpec
from afre.schema import Artifact


def nonlinear_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE nl_artifacts (fingerprint TEXT PRIMARY KEY NOT "
            "NULL, type_name TEXT NOT NULL, schema_version TEXT NOT NULL, "
            "payload TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE nl_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "interaction_id TEXT, source_id TEXT, feature_id TEXT, family "
            "TEXT, target_id TEXT, horizon_id TEXT, security_id TEXT, "
            "origin_ns INTEGER, model_id TEXT, spec_id TEXT, available_ns "
            "INTEGER, cutoff_ns INTEGER, test_id TEXT)"
        ),
        (
            "CREATE TABLE nl_links (fingerprint TEXT NOT NULL, reference_id "
            "TEXT NOT NULL, PRIMARY KEY (fingerprint, reference_id))"
        ),
        "CREATE INDEX nl_interaction_idx ON nl_records (interaction_id, available_ns)",
        "CREATE INDEX nl_source_idx ON nl_records (source_id, feature_id, available_ns)",
        "CREATE INDEX nl_family_idx ON nl_records (family, target_id, horizon_id)",
        "CREATE INDEX nl_origin_idx ON nl_records (security_id, origin_ns, target_id)",
        "CREATE INDEX nl_model_idx ON nl_records (model_id, spec_id, available_ns)",
        "CREATE INDEX nl_evaluation_idx ON nl_records (model_id, cutoff_ns, test_id)",
        "CREATE INDEX nl_reference_idx ON nl_links (reference_id, fingerprint)",
    ]
    for table in ("nl_artifacts", "nl_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} WHEN "
            f"EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
    for table in ("nl_artifacts", "nl_records", "nl_links"):
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE {operation} "
                f"ON {table} BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def nonlinear_index(value: Artifact) -> tuple[object, ...]:
    interaction = source = feature = family = target = horizon = security = origin = model = (
        spec
    ) = available = cutoff = test = None
    if isinstance(value, InteractionDefinition):
        interaction = value.interaction_id
    elif isinstance(value, ScalarInput):
        source, feature, security, origin, available = (
            value.source_id,
            value.definition.fingerprint,
            value.origin.instrument.fingerprint,
            value.origin.timestamp_ns,
            value.available_ns,
        )
    elif isinstance(value, InteractionSet):
        target, horizon = value.target.fingerprint, value.target.horizon.fingerprint
    elif isinstance(value, NonlinearModelSpec):
        spec, family, target, horizon, cutoff = (
            value.fingerprint,
            value.family.value,
            value.target.fingerprint,
            value.target.horizon.fingerprint,
            value.cutoff_ns,
        )
    elif isinstance(value, FittedTransformArtifact):
        interaction, available, cutoff = (
            value.definition_id,
            value.available_ns,
            value.cutoff_ns,
        )
    elif isinstance(value, InteractionValue):
        interaction, available = value.definition_id, value.available_ns
    elif isinstance(value, InteractionMatrix):
        spec, cutoff, available = value.spec_id, value.cutoff_ns, value.computed_ns
    elif isinstance(value, NonlinearModelArtifact):
        model, spec, family, available, cutoff = (
            value.fingerprint,
            value.spec_id,
            value.family.value,
            value.available_ns,
            value.cutoff_ns,
        )
    elif isinstance(value, NonlinearForecast):
        model, spec, target, security, origin, available = (
            value.model_id,
            value.spec_id,
            value.target_definition_id,
            value.security.instrument.fingerprint,
            value.origin.timestamp_ns,
            value.available_ns,
        )
    elif isinstance(value, NonlinearEvaluation):
        model, cutoff, available, test = (
            value.model_id,
            value.cutoff_ns,
            value.available_ns,
            value.test_evaluation_id,
        )
    return (
        value.fingerprint,
        interaction,
        source,
        feature,
        family,
        target,
        horizon,
        security,
        origin,
        model,
        spec,
        available,
        cutoff,
        test,
    )
