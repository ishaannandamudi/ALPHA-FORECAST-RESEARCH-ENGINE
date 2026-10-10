"""Native monitoring evidence without refitting, recalibrating or changing source weights."""

from dataclasses import dataclass

from afre.costs import CostResearchEngine
from afre.health import (
    HealthDiagnostic,
    HealthDiagnosticRequest,
    HealthDirection,
    HealthEngine,
    HealthObservation,
    HealthRepository,
    HealthRule,
    HealthSpec,
    HealthStatistic,
    ModelHealthSnapshot,
    MonitoredArtifactReference,
    MonitoringWindow,
)
from afre.health.context import context_records
from afre.invariance import InvarianceEngine
from afre.invariance.artifacts import EnvironmentMembership
from afre.schema import require
from afre.uncertainty.sources import source_for
from examples.costs_fixture import declare_scenario
from examples.invariance_cohorts import Cohorts, build_cohorts
from examples.invariance_fixture import InvarianceFixture, build_fixture


@dataclass(frozen=True)
class NativeHealthFixture:
    upstream: InvarianceFixture
    cohorts: Cohorts
    cost_evaluation_id: str
    cost_sample_ids: tuple[str, ...]
    stability_ids: tuple[str, ...]


def build_native(repo: HealthRepository) -> NativeHealthFixture:
    f = build_fixture(repo)
    cohorts = build_cohorts(repo, f)
    stability = InvarianceEngine(repo).evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
    scenario, _ = declare_scenario(repo, f.spec)
    cost = CostResearchEngine(repo)
    path, totals = cost.estimate(scenario.fingerprint, 100)
    result = cost.evaluate(path.fingerprint, tuple(t.fingerprint for t in totals), 100, 100)
    return NativeHealthFixture(
        f,
        cohorts,
        result.fingerprint,
        result.sample_evaluation_ids,
        tuple(m.fingerprint for m in stability),
    )


def declared_spec(
    repo: HealthRepository,
    reference: MonitoredArtifactReference,
    observations: tuple[HealthObservation, ...],
    kinds: tuple[HealthDiagnostic, ...],
    *,
    minimum: int = 1,
    column: str = "prediction",
    declaration: int | None = None,
    predeclared: bool = True,
    comparisons: tuple[str, ...] = (),
    environment: str | None = None,
    memberships: tuple[str, ...] = (),
    context: tuple[str, ...] = (),
) -> tuple[HealthSpec, tuple[HealthRule, ...]]:
    times = sorted({r.valid_ns for r in observations})
    require(bool(times), "health fixture requires native evidence")
    a, b = (times[0], times[1]) if len(times) > 1 else (times[0], times[0])
    cutoff = max(100, b + 1)
    at = reference.available_ns if declaration is None else declaration
    requests = tuple(HealthDiagnosticRequest(k, column, minimum) for k in kinds)
    rules = tuple(
        HealthRule(
            k.value,
            k,
            HealthDirection.ABSOLUTE_CHANGE_WORSE,
            HealthStatistic.DELTA,
            minimum,
            0.5,
            2.0,
            at,
        )
        for k in kinds
    )
    by_kind = {r.kind: r for r in rules}
    spec = HealthSpec(
        "native-health",
        reference.fingerprint,
        reference.target_id,
        reference.horizon_id,
        MonitoringWindow("reference", a, a + 1, cutoff, minimum),
        MonitoringWindow("current", b, b + 1, cutoff, minimum),
        requests,
        tuple((q.fingerprint, by_kind[q.kind].fingerprint) for q in requests),
        tuple(r.fingerprint for r in observations if r.valid_ns == a),
        tuple(r.fingerprint for r in observations if r.valid_ns == b),
        minimum,
        at,
        comparison_reference_ids=comparisons,
        predeclared=predeclared,
        allow_overlap=a == b,
        environment_id=environment,
        membership_ids=memberships,
        context_ids=context,
        context_records=context_records(repo, context),
    )
    return spec, rules


def native_monitor(
    repo: HealthRepository,
    source_ids: tuple[str, ...],
    kinds: tuple[HealthDiagnostic, ...],
    column: str = "prediction",
) -> ModelHealthSnapshot:
    e = HealthEngine(repo)
    ref = e.monitor(source_ids[0])
    rows = tuple(e.observe(ref.fingerprint, i, 100) for i in source_ids)
    spec, rules = declared_spec(
        repo,
        ref,
        rows,
        kinds,
        column=column,
        predeclared=ref.available_ns <= min(r.valid_ns for r in rows),
    )
    e.declare(spec, rules)
    return e.evaluate(spec.fingerprint, max(100, spec.current_window.evaluation_cutoff_ns))


def matching_family(repo: HealthRepository, identities: tuple[str, ...]) -> tuple[str, ...]:
    ref = source_for(repo, identities[0])
    return tuple(i for i in identities if source_for(repo, i).model_id == ref.model_id)


def cohort_monitor(
    repo: HealthRepository, f: NativeHealthFixture, environment_id: str
) -> ModelHealthSnapshot:
    e = HealthEngine(repo)
    ids = f.upstream.spec.forecast_ids
    ref = e.monitor(ids[0])
    rows = tuple(e.observe(ref.fingerprint, i, 100) for i in ids)
    members = tuple(
        i
        for i in f.cohorts.membership_ids
        if repo.get(EnvironmentMembership, i).environment_id == environment_id
    )
    # Declare the complete native environment and source set, including zero-membership rows.
    spec, rules = declared_spec(
        repo,
        ref,
        rows,
        (HealthDiagnostic.PREDICTION_MEAN,),
        minimum=2,
        declaration=40,
        environment=environment_id,
        memberships=members,
    )
    e.declare(spec, rules)
    return e.evaluate(spec.fingerprint, max(100, spec.current_window.evaluation_cutoff_ns))


def parameter_monitor(
    repo: HealthRepository,
    reference_id: str,
    current_id: str,
    kinds: tuple[HealthDiagnostic, ...],
    column: str = "parameter",
    anchors: tuple[str | None, str | None] = (None, None),
) -> ModelHealthSnapshot:
    e = HealthEngine(repo)
    a, b = e.monitor(reference_id, anchors[0]), e.monitor(current_id, anchors[1])
    ra, rb = (
        e.observe(a.fingerprint, reference_id, 100),
        e.observe(b.fingerprint, current_id, 100),
    )
    q = tuple(HealthDiagnosticRequest(k, column, 1) for k in kinds)
    rules = tuple(
        HealthRule(
            k.value, k, HealthDirection.HIGHER_WORSE, HealthStatistic.DELTA, 1, 0.5, 2.0, 100
        )
        for k in kinds
    )
    bindings = {r.kind: r for r in rules}
    start_a, start_b = sorted((ra.valid_ns, rb.valid_ns))
    spec = HealthSpec(
        "explicit-fitted-parameter-comparison",
        a.fingerprint,
        a.target_id,
        a.horizon_id,
        MonitoringWindow("reference-fit", start_a, start_a + 1, 100, 1),
        MonitoringWindow("current-fit", start_b, start_b + 1, 100, 1),
        q,
        tuple((r.fingerprint, bindings[r.kind].fingerprint) for r in q),
        (ra.fingerprint,),
        (rb.fingerprint,),
        1,
        100,
        comparison_reference_ids=(b.fingerprint,) if b != a else (),
        allow_overlap=start_a == start_b,
        predeclared=False,
    )
    e.declare(spec, rules)
    return e.evaluate(spec.fingerprint, max(100, spec.current_window.evaluation_cutoff_ns))
