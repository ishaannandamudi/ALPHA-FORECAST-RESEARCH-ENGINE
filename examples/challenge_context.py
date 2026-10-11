"""Explicit native health snapshots and economically identical source-bound cost evidence."""

from dataclasses import replace

from afre.challenger import (
    ChallengeCostPlan,
    ChallengeProgram,
    ChallengeRepository,
    ParticipantReference,
)
from afre.costs import CostResearchEngine
from afre.fusion.artifacts import FusedForecast
from afre.health import (
    HealthDiagnostic,
    HealthDiagnosticRequest,
    HealthDirection,
    HealthEngine,
    HealthRule,
    HealthSpec,
    HealthStatistic,
    MonitoringWindow,
)
from afre.invariance import (
    EnvironmentDefinition,
    EnvironmentKind,
    EnvironmentRule,
    EnvironmentSet,
    InvarianceEngine,
    StabilityAnalysisSpec,
    StabilityMetricName,
    StabilityTimeWindow,
)
from afre.target_engine.definitions import TargetDefinition
from examples.challenge_native import sample_origin
from examples.challenger_fixture import ChallengeFixture
from examples.costs_fixture import declare_scenario


def health_context_for(
    repo: ChallengeRepository,
    fixture: ChallengeFixture,
    program: ChallengeProgram,
    *,
    warning_threshold: float = 0.5,
) -> tuple[tuple[str, str], ...]:
    return health_bindings_for(
        repo,
        fixture.participants,
        fixture.outputs,
        program,
        warning_threshold=warning_threshold,
    )


def health_bindings_for(
    repo: ChallengeRepository,
    participants: tuple[ParticipantReference, ...],
    output_bindings: tuple[tuple[str, tuple[str, ...]], ...],
    program: ChallengeProgram,
    *,
    warning_threshold: float = 0.5,
) -> tuple[tuple[str, str], ...]:
    engine = HealthEngine(repo)
    result = []
    request = HealthDiagnosticRequest(HealthDiagnostic.PREDICTION_MEAN, "prediction", 1)
    rule = HealthRule(
        "explicit-challenge-health",
        request.kind,
        HealthDirection.HIGHER_WORSE,
        HealthStatistic.DELTA,
        1,
        warning_threshold,
        2.0,
        0,
    )
    for participant, outputs in output_bindings:
        ref = next(p.reference for p in participants if p.fingerprint == participant)
        rows = tuple(
            engine.observe(ref.fingerprint, identity, 120)
            for identity in outputs
            if program.window.contains(sample_origin(repo, identity)[1])
        )
        window = MonitoringWindow(
            "shared-challenge-window",
            program.window.start_ns,
            program.window.end_ns,
            program.window.cutoff_ns,
            1,
        )
        spec = HealthSpec(
            "explicit-challenge-health",
            ref.fingerprint,
            program.target_id,
            program.horizon_id,
            window,
            window,
            (request,),
            ((request.fingerprint, rule.fingerprint),),
            tuple(r.fingerprint for r in rows),
            tuple(r.fingerprint for r in rows),
            1,
            program.declared_ns,
            allow_overlap=True,
            predeclared=program.predeclared,
        )
        engine.declare(spec, (rule,))
        result.append((participant, engine.evaluate(spec.fingerprint, 120).fingerprint))
    return tuple(sorted(result))


def cost_context_for(
    repo: ChallengeRepository,
    fixture: ChallengeFixture,
    program: ChallengeProgram,
    *,
    fee: float = 0.01,
) -> tuple[ChallengeCostPlan, tuple[tuple[str, str], ...]]:
    engine = CostResearchEngine(repo)
    target = repo.get(TargetDefinition, program.target_id)
    environment = EnvironmentDefinition(
        "challenge-time",
        EnvironmentKind.TIME_WINDOW,
        "challenge time",
        "1",
        "AFRE-declared",
        EnvironmentRule.TIME,
        target,
        0,
        window=StabilityTimeWindow(program.window.start_ns, program.window.end_ns),
    )
    envset = InvarianceEngine(repo).declare(EnvironmentSet((environment,), 0))
    result, scenarios = [], []
    for participant, outputs in fixture.outputs:
        selected = tuple(
            repo.get(FusedForecast, i)
            for i in outputs
            if program.window.contains(repo.get(FusedForecast, i).origin.timestamp_ns)
        )
        spec = StabilityAnalysisSpec(
            target,
            program.fold_id,
            envset.fingerprint,
            tuple(s.sample_id for s in selected),
            tuple(s.fingerprint for s in selected),
            (StabilityMetricName.MAE,),
            0,
        )
        scenario, _ = declare_scenario(repo, spec, publish=False)
        scenario = replace(scenario, scenario_id="challenge-economics")
        if fee != 0.01:
            from examples.costs_workflow import component_variant

            component = next(c for c in scenario.components if c.name == "fee")
            scenario = component_variant(
                scenario, replace(component, fixed_value=fee), "challenge-economics", fixed=True
            )
        engine.declare(scenario)
        path, totals = engine.estimate(scenario.fingerprint, 120)
        evaluation = engine.evaluate(
            path.fingerprint,
            tuple(t.fingerprint for t in totals),
            program.window.cutoff_ns,
            120,
        )
        scenarios.append(scenario)
        result.append((participant, evaluation.fingerprint))
    plan = ChallengeCostPlan("explicit-shared-economics", scenarios[0].fingerprint, 0)
    from afre.challenger import ChallengeEngine

    ChallengeEngine(repo).publish((plan,))
    return plan, tuple(sorted(result))
