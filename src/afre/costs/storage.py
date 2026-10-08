"""Additive SQLite19 tables/indexes/triggers; earlier DDL and metadata remain exact."""

from afre.costs.artifacts import (
    CostAwareEvaluation,
    CostAwareSampleEvaluation,
    CostComponentEstimate,
    ResearchExposureChange,
    TotalCostEstimate,
)
from afre.costs.cost_inputs import CostInputReference
from afre.costs.definitions import CostScenario
from afre.invariance.storage import METADATA as PREVIOUS_METADATA
from afre.invariance.storage import all_statements as previous_statements
from afre.schema import Artifact

METADATA = {
    **PREVIOUS_METADATA,
    "cost_research_store_schema_version": "1.18",
    "cost_research_schema": "1.0",
    "cost_research_engine_version": "0.19.0",
}


def costs_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE cost_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT "
            "NOT NULL)"
        ),
        (
            "CREATE TABLE cost_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "scenario_id TEXT, source_id TEXT, component_id TEXT, provider TEXT, "
            "security_id TEXT, origin_ns INTEGER, target_id TEXT, horizon_id "
            "TEXT, timing TEXT, cutoff_ns INTEGER, test_id TEXT, available_ns "
            "INTEGER, change_id TEXT)"
        ),
        (
            "CREATE TABLE cost_links (fingerprint TEXT NOT NULL, reference_id "
            "TEXT NOT NULL, PRIMARY KEY (fingerprint, reference_id))"
        ),
        "CREATE INDEX cost_scenario_idx ON cost_records (scenario_id, source_id)",
        "CREATE INDEX cost_component_idx ON cost_records (component_id, provider)",
        "CREATE INDEX cost_origin_idx ON cost_records (security_id, origin_ns)",
        "CREATE INDEX cost_target_idx ON cost_records (target_id, horizon_id)",
        "CREATE INDEX cost_timing_idx ON cost_records (timing, cutoff_ns, test_id)",
        "CREATE INDEX cost_change_idx ON cost_records (change_id, scenario_id)",
        "CREATE INDEX cost_reference_idx ON cost_links (reference_id, fingerprint)",
    ]
    for table in ("cost_artifacts", "cost_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} "
            f"WHEN EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
    for table in ("cost_artifacts", "cost_records", "cost_links"):
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE "
                f"{operation} ON {table} BEGIN SELECT "
                "RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def all_statements() -> tuple[str, ...]:
    return (*previous_statements(), *costs_schema())


def costs_index(v: Artifact) -> tuple[object, ...]:
    scenario = source = component = provider = security = origin = target = horizon = timing = (
        cutoff
    ) = test = available = change = None
    if isinstance(v, CostInputReference):
        source, component, provider, security, origin, available = (
            v.source.fingerprint,
            v.component.value,
            v.provider,
            v.security.fingerprint,
            v.as_of_ns,
            v.clocks.final_available_ns,
        )
    elif isinstance(v, CostScenario):
        scenario, target, horizon, timing = (
            v.fingerprint,
            v.target.fingerprint,
            v.target.horizon.fingerprint,
            v.timing.value,
        )
    elif isinstance(v, ResearchExposureChange):
        scenario, source, security, origin, available, change = (
            v.scenario_id,
            v.source_id,
            v.origin.instrument.fingerprint,
            v.origin.timestamp_ns,
            v.available_ns,
            v.fingerprint,
        )
    elif isinstance(v, CostComponentEstimate):
        scenario, component, timing, available, change = (
            v.scenario_id,
            v.component_id,
            v.timing.value,
            v.available_ns,
            v.change_id,
        )
    elif isinstance(v, TotalCostEstimate):
        scenario, timing, available, change = (
            v.scenario_id,
            v.timing.value,
            v.available_ns,
            v.change_id,
        )
    elif isinstance(v, CostAwareSampleEvaluation):
        scenario, source, security, origin, target, horizon, cutoff, available, change = (
            v.scenario_id,
            v.source_id,
            v.origin.instrument.fingerprint,
            v.origin.timestamp_ns,
            v.target_id,
            v.horizon_id,
            v.evaluation_cutoff_ns,
            v.available_ns,
            v.change_id,
        )
    elif isinstance(v, CostAwareEvaluation):
        scenario, timing, cutoff, test, available = (
            v.scenario_id,
            v.timing.value,
            v.evaluation_cutoff_ns,
            v.test_evaluation_id,
            v.available_ns,
        )
    else:
        scenario, component, available = (
            getattr(v, "scenario_id", None),
            getattr(v, "component_id", None),
            getattr(v, "available_ns", None),
        )
    return (
        v.fingerprint,
        scenario,
        source,
        component,
        provider,
        security,
        origin,
        target,
        horizon,
        timing,
        cutoff,
        test,
        available,
        change,
    )
