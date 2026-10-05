"""Additive immutable JSON and independently verified indexed projections."""

from afre.mixture.artifacts import GateModelArtifact, MixtureEvaluation, MixtureForecast
from afre.mixture.definitions import ExpertSet, FixedGateSpec, LearnedGateSpec
from afre.mixture.experts import ExpertForecastBinding, ExpertReference, ExternalExpertForecast
from afre.schema import Artifact


def mixture_schema() -> tuple[str, ...]:
    statements = [
        "CREATE TABLE mix_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
        "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT NOT NULL)",
        "CREATE TABLE mix_records (fingerprint TEXT PRIMARY KEY NOT NULL, expert_id TEXT, "
        "kind TEXT, provider TEXT, target_id TEXT, horizon_id TEXT, security_id TEXT, "
        "origin_ns INTEGER, gate_mode TEXT, gate_id TEXT, available_ns INTEGER, "
        "missingness TEXT, cutoff_ns INTEGER, test_id TEXT)",
        "CREATE INDEX mix_expert_idx ON mix_records (expert_id, kind, provider, available_ns)",
        "CREATE INDEX mix_origin_idx ON mix_records "
        "(target_id, horizon_id, security_id, origin_ns)",
        "CREATE INDEX mix_gate_idx ON mix_records (gate_mode, gate_id, available_ns)",
        "CREATE INDEX mix_missing_idx ON mix_records (missingness, origin_ns)",
        "CREATE INDEX mix_eval_idx ON mix_records (gate_id, cutoff_ns, test_id)",
    ]
    for table in ("mix_artifacts", "mix_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} WHEN "
            f"EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE {operation} "
                f"ON {table} BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def mixture_index(value: Artifact) -> tuple[object, ...]:
    expert = kind = provider = target = horizon = security = origin = mode = gate = (
        available
    ) = missing = cutoff = test = None
    if isinstance(value, ExpertReference):
        expert, kind, provider, target, horizon, available = (
            value.fingerprint,
            value.kind.value,
            value.provider,
            value.target.fingerprint,
            value.target.horizon.fingerprint,
            value.available_ns,
        )
    elif isinstance(value, ExternalExpertForecast):
        expert, kind, provider, target, horizon, security, origin, available, missing = (
            value.expert.fingerprint,
            value.expert.kind.value,
            value.expert.provider,
            value.expert.target.fingerprint,
            value.expert.target.horizon.fingerprint,
            value.origin.instrument.fingerprint,
            value.origin.timestamp_ns,
            value.clocks.final_available_ns,
            value.quality.value,
        )
    elif isinstance(value, ExpertForecastBinding):
        expert, target, security, origin, available, missing = (
            value.expert_id,
            value.target_definition_id,
            value.origin.instrument.fingerprint,
            value.origin.timestamp_ns,
            value.available_ns,
            value.quality.value,
        )
    elif isinstance(value, ExpertSet):
        target, horizon, missing = (
            value.target.fingerprint,
            value.target.horizon.fingerprint,
            value.missing_policy.value,
        )
    elif isinstance(value, FixedGateSpec):
        gate, mode, target, horizon, available = (
            value.fingerprint,
            "fixed",
            value.expert_set.target.fingerprint,
            value.expert_set.target.horizon.fingerprint,
            value.available_ns,
        )
    elif isinstance(value, LearnedGateSpec):
        gate, mode, target, horizon, cutoff = (
            value.fingerprint,
            "learned_linear",
            value.expert_set.target.fingerprint,
            value.expert_set.target.horizon.fingerprint,
            value.cutoff_ns,
        )
    elif isinstance(value, GateModelArtifact):
        gate, mode, available, cutoff = (
            value.fingerprint,
            "learned_linear",
            value.available_ns,
            value.cutoff_ns,
        )
    elif isinstance(value, MixtureForecast):
        gate, mode, target, security, origin, available, missing = (
            value.request.gate_id,
            value.gating_mode.value,
            value.target_definition_id,
            value.origin.instrument.fingerprint,
            value.origin.timestamp_ns,
            value.available_ns,
            "fallback"
            if value.fallback_id
            else "missing"
            if any(c.reason != "available" for c in value.contributions)
            else "complete",
        )
    elif isinstance(value, MixtureEvaluation):
        gate, cutoff, available, test = (
            value.gate_id,
            value.cutoff_ns,
            value.available_ns,
            value.test_evaluation_id,
        )
    return (
        value.fingerprint,
        expert,
        kind,
        provider,
        target,
        horizon,
        security,
        origin,
        mode,
        gate,
        available,
        missing,
        cutoff,
        test,
    )
