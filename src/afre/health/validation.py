"""Semantic replay of every completed health artifact and its exact evidence."""

from typing import TYPE_CHECKING

from afre.health.artifacts import (
    HealthDecayTrend,
    HealthMetric,
    HealthObservation,
    ModelHealthSnapshot,
)
from afre.health.definitions import (
    HealthDiagnosticRequest,
    HealthRule,
    HealthSpec,
    MonitoredArtifactReference,
)
from afre.health.evaluation import metric_for, snapshot_for
from afre.health.inputs import input_for
from afre.health.lineage import HealthAudit, audit_for
from afre.health.sources import observation_for, validate_reference
from afre.health.trends import trend_for
from afre.invariance.definitions import EnvironmentDefinition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository


def validate_spec(repo: "HealthRepository", value: HealthSpec) -> None:
    primary = repo.get(MonitoredArtifactReference, value.reference_id)
    require(
        (primary.target_id, primary.horizon_id) == (value.target_id, value.horizon_id),
        "health primary exact target/horizon",
    )
    refs = (
        primary,
        *(repo.get(MonitoredArtifactReference, i) for i in value.comparison_reference_ids),
    )
    require(
        all(r.available_ns <= value.declared_ns for r in refs),
        "health frozen reference available at declaration",
    )
    for window in (value.reference_window, value.current_window):
        require(
            repo.get(type(window), window.fingerprint) == window,
            "health exact persisted window",
        )
    require(
        repo.get(type(value.bounds), value.bounds.fingerprint) == value.bounds,
        "health persisted configured bounds",
    )
    for request in value.requests:
        require(
            repo.get(HealthDiagnosticRequest, request.fingerprint) == request,
            "health exact request",
        )
    for request_id, rule_id in value.rule_bindings:
        rule = repo.get(HealthRule, rule_id)
        request = repo.get(HealthDiagnosticRequest, request_id)
        require(
            rule.kind is request.kind and rule.declared_ns <= value.declared_ns,
            "health exact predeclared rule/kind",
        )
    allowed = {r.fingerprint for r in refs}
    for identity in (*value.reference_observation_ids, *value.current_observation_ids):
        require(
            repo.get(HealthObservation, identity).reference_id in allowed,
            "health explicit frozen observation/reference set",
        )
    if value.environment_id:
        environment = repo.get(EnvironmentDefinition, value.environment_id)
        require(
            environment.target.fingerprint == value.target_id
            and environment.declared_ns <= value.declared_ns,
            "health PIT declared environment target/time",
        )
    if value.test_evaluation_id:
        seal = repo.get(TestEvaluation, value.test_evaluation_id)
        require(
            seal.fold_id == primary.fold_id
            and seal.evaluated_ns
            == max(
                value.reference_window.evaluation_cutoff_ns,
                value.current_window.evaluation_cutoff_ns,
            ),
            "health exact declared TEST context",
        )
    from afre.health.context import context_records, verify_context

    verify_context(repo, value.context_records)
    if not repo._feature_only_depth:
        require(
            context_records(repo, value.context_ids) == value.context_records,
            "health exact declared native context",
        )
    require(
        all(
            at
            <= max(
                value.reference_window.evaluation_cutoff_ns,
                value.current_window.evaluation_cutoff_ns,
            )
            for _, _, at, _ in value.context_records
        ),
        "health context unavailable at monitoring cutoff",
    )


def validate_health(repo: "HealthRepository", value: Artifact) -> None:
    if isinstance(value, MonitoredArtifactReference):
        validate_reference(repo, value)
    elif isinstance(value, HealthSpec):
        validate_spec(repo, value)
    elif isinstance(value, HealthObservation):
        ref = repo.resolve(MonitoredArtifactReference, value.reference_id)
        if "input-grid" in value.quality:
            require(value.sample_id is not None, "health input exact sample")
            assert value.sample_id is not None
            expected = input_for(
                repo, ref, value.source_id, value.sample_id, value.constructed_ns
            )
        else:
            expected = observation_for(repo, ref, value.source_id, value.constructed_ns)
        require(value == expected, "health observation semantic replay")
    elif isinstance(value, HealthMetric):
        spec = repo.resolve(HealthSpec, value.spec_id)
        request = repo.resolve(HealthDiagnosticRequest, value.request_id)
        require(
            request in spec.requests
            and value == metric_for(repo, spec, request, value.available_ns),
            "health metric semantic replay",
        )
    elif isinstance(value, ModelHealthSnapshot):
        spec = repo.resolve(HealthSpec, value.spec_id)
        metrics = tuple(repo.resolve(HealthMetric, i) for i in value.metric_ids)
        require(
            value == snapshot_for(spec, metrics, value.available_ns),
            "health snapshot semantic replay",
        )
    elif isinstance(value, HealthDecayTrend):
        require(
            value == trend_for(repo, value.metric_ids, value.available_ns),
            "health trend semantic replay",
        )
    elif isinstance(value, HealthAudit):
        require(value == audit_for(repo, value.root_id), "health audit semantic replay")
