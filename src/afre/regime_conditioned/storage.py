"""Additive immutable safe JSON with independently verified indexed projections."""

from afre.regime_conditioned.artifacts import (
    RegimeCalibrationAssessment,
    RegimeConditionedEvaluation,
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditionedSample,
    RegimeDriftDiagnostic,
    RegimeMatchSet,
    RegimeTransition,
)
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.regime_conditioned.regimes import (
    RegimeProviderReference,
    RegimeSnapshot,
    RegimeTaxonomy,
)
from afre.schema import Artifact


def regime_schema() -> tuple[str, ...]:
    statements = [
        "CREATE TABLE rc_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT NOT NULL)",
        "CREATE TABLE rc_records (fingerprint TEXT PRIMARY KEY NOT NULL, provider TEXT, "
        "taxonomy_id TEXT, state_id TEXT, scope TEXT, subject_id TEXT, as_of_ns INTEGER, "
        "available_ns INTEGER, origin_ns INTEGER, target_id TEXT, horizon_id TEXT, "
        "spec_id TEXT, "
        "base_model_id TEXT, model_id TEXT, cutoff_ns INTEGER, transition_ns INTEGER, "
        "previous_id TEXT, current_id TEXT, reference_evaluation_id TEXT, "
        "current_evaluation_id TEXT, test_id TEXT)",
        "CREATE INDEX rc_snapshot_idx ON rc_records "
        "(provider, taxonomy_id, scope, subject_id, as_of_ns, available_ns)",
        "CREATE INDEX rc_state_idx ON rc_records (taxonomy_id, state_id, available_ns)",
        "CREATE INDEX rc_origin_idx ON rc_records (origin_ns, target_id, horizon_id)",
        "CREATE INDEX rc_model_idx ON rc_records (spec_id, base_model_id, model_id, cutoff_ns)",
        "CREATE INDEX rc_transition_idx ON rc_records "
        "(taxonomy_id, transition_ns, previous_id, current_id)",
        "CREATE INDEX rc_drift_idx ON rc_records "
        "(reference_evaluation_id, current_evaluation_id, cutoff_ns)",
        "CREATE INDEX rc_test_idx ON rc_records (test_id, cutoff_ns)",
    ]
    for table in ("rc_artifacts", "rc_records"):
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


def regime_index(value: Artifact) -> tuple[object, ...]:
    provider = taxonomy = state = scope = subject = asof = available = origin = target = (
        horizon
    ) = spec = base = model = cutoff = transition = previous = current = reference_eval = (
        current_eval
    ) = test = None
    if isinstance(value, RegimeProviderReference):
        provider = value.provider
    elif isinstance(value, RegimeTaxonomy):
        provider, taxonomy = value.provider.provider, value.fingerprint
    elif isinstance(value, RegimeSnapshot):
        provider, taxonomy, state, scope, subject, asof, available = (
            value.taxonomy.provider.provider,
            value.taxonomy.fingerprint,
            value.membership.hard_state,
            value.subject.scope.value,
            value.subject.fingerprint,
            value.as_of_ns,
            value.clocks.final_available_ns,
        )
    elif isinstance(value, RegimeConditioningSpec):
        spec, base, target, horizon, taxonomy, scope = (
            value.fingerprint,
            value.base_model_id,
            value.target.fingerprint,
            value.target.horizon.fingerprint,
            value.taxonomy_id,
            value.scope.value,
        )
    elif isinstance(value, RegimeMatchSet):
        spec = value.spec_id
    elif isinstance(value, RegimeConditionedSample):
        spec, subject, origin = (
            value.spec_id,
            value.security.fingerprint,
            value.origin.timestamp_ns,
        )
    elif isinstance(value, RegimeConditionedModel):
        model, spec, cutoff, available = (
            value.fingerprint,
            value.spec_id,
            value.cutoff_ns,
            value.available_ns,
        )
    elif isinstance(value, RegimeConditionedForecast):
        model, spec, subject, origin, available, target = (
            value.model_id,
            value.spec_id,
            value.security.fingerprint,
            value.origin.timestamp_ns,
            value.available_ns,
            value.target_definition_id,
        )
    elif isinstance(value, RegimeTransition):
        taxonomy, transition, previous, current, available = (
            value.taxonomy_id,
            value.transition_ns,
            value.previous_id,
            value.current_id,
            value.available_ns,
        )
    elif isinstance(value, RegimeConditionedEvaluation):
        model, cutoff, available, test = (
            value.model_id,
            value.cutoff_ns,
            value.available_ns,
            value.test_evaluation_id,
        )
    elif isinstance(value, RegimeCalibrationAssessment):
        cutoff = value.cutoff_ns
    elif isinstance(value, RegimeDriftDiagnostic):
        reference_eval, current_eval, cutoff = (
            value.reference_evaluation_id,
            value.current_evaluation_id,
            value.cutoff_ns,
        )
    return (
        value.fingerprint,
        provider,
        taxonomy,
        state,
        scope,
        subject,
        asof,
        available,
        origin,
        target,
        horizon,
        spec,
        base,
        model,
        cutoff,
        transition,
        previous,
        current,
        reference_eval,
        current_eval,
        test,
    )
