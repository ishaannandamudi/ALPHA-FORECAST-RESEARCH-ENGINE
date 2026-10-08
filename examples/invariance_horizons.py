"""Actual independent 1h/1d targets, each with its own frozen stability assessment."""

from afre.invariance import (
    EnvironmentDefinition,
    EnvironmentKind,
    EnvironmentMetric,
    EnvironmentRule,
    EnvironmentSet,
    InvarianceEngine,
    InvarianceRepository,
    StabilityAnalysisSpec,
    StabilityMetricName,
    StabilityTimeWindow,
)
from afre.invariance.forecasts import forecast_source
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.splits import FoldDefinition
from examples.regime_horizon_fixture import real_horizons


def horizon_analyses(repo: InvarianceRepository) -> tuple[EnvironmentMetric, ...]:
    engine = InvarianceEngine(repo)
    outputs: list[EnvironmentMetric] = []
    for _, forecasts in real_horizons(repo):
        sources = tuple(forecast_source(repo, p.fingerprint) for p in forecasts)
        first = sources[0]
        declared = repo.get(FoldDefinition, first.fold_id).training_cutoff_ns
        start, end = (
            min(s.origin.timestamp_ns for s in sources),
            max(s.origin.timestamp_ns for s in sources) + 1,
        )
        d = EnvironmentDefinition(
            "real-" + first.target.horizon.fingerprint,
            EnvironmentKind.TIME_WINDOW,
            "actual horizon research window",
            "1",
            "AFRE-declared",
            EnvironmentRule.TIME,
            first.target,
            declared,
            window=StabilityTimeWindow(start, end),
        )
        envs = engine.declare(EnvironmentSet((d,), declared))
        spec = engine.register(
            StabilityAnalysisSpec(
                first.target,
                first.fold_id,
                envs.fingerprint,
                tuple(s.sample_id for s in sources),
                tuple(p.fingerprint for p in forecasts),
                (StabilityMetricName.MAE,),
                declared,
            )
        )
        members = tuple(
            engine.bind(
                d.fingerprint, s.sample_id, constructed_ns=s.origin.timestamp_ns
            ).fingerprint
            for s in sources
        )
        cutoff = max(
            repo.get(ResearchSample, s.sample_id).target_available_ns or 0 for s in sources
        )
        cutoff = max(cutoff, end)
        outputs.extend(engine.evaluate(spec.fingerprint, members, cutoff, cutoff))
    return tuple(outputs)
