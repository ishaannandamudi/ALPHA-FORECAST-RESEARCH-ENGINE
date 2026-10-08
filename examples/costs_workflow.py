"""Supplied scenarios, matched native sources and immutable correction examples."""

from dataclasses import replace

from afre.costs import (
    CostComponentSpec,
    CostResearchEngine,
    CostResearchRepository,
    CostScenario,
)
from afre.costs.artifacts import CostAwareEvaluation, ResearchExposurePath, TotalCostEstimate
from afre.costs.cost_inputs import CostInputReference
from afre.orthogonalization import OrthogonalSignalValue
from afre.research_datasets.schema import Partition
from afre.uncertainty.sources import source_for
from examples.costs_fixture import CostFixture
from examples.invariance_fixture import native_forecasts


def subset_source(
    repo: CostResearchRepository,
    base: CostScenario,
    source_ids: tuple[str, ...],
    tag: str,
    *,
    unit: str = "return_fraction",
    uncertainty_ids: tuple[str, ...] = (),
) -> CostScenario:
    samples = {
        v.sample_id
        if isinstance((v := repo.get_any(i)), OrthogonalSignalValue)
        else source_for(repo, i).sample_id
        for i in source_ids
    }
    return replace(
        base,
        scenario_id=tag,
        source_ids=source_ids,
        sample_ids=tuple(samples),
        bindings=tuple(b for b in base.bindings if b.sample_id in samples),
        liquidity=tuple(a for a in base.liquidity if a.sample_id in samples),
        signal_unit=unit,
        uncertainty_ids=uncertainty_ids,
    )


def corrected_input(base: CostScenario, old_id: str, value: CostInputReference) -> CostScenario:
    return replace(
        base,
        scenario_id=base.scenario_id + "-revision2",
        bindings=tuple(
            replace(
                b, input_ids=tuple(value.fingerprint if i == old_id else i for i in b.input_ids)
            )
            for b in base.bindings
        ),
    )


def assess(
    engine: CostResearchEngine,
    scenario: CostScenario,
    at: int = 100,
    *,
    test_identity: str | None = None,
) -> tuple[ResearchExposurePath, tuple[TotalCostEstimate, ...], CostAwareEvaluation]:
    engine.declare(scenario)
    path, totals = engine.estimate(scenario.fingerprint, at)
    evaluation = engine.evaluate(
        path.fingerprint, tuple(t.fingerprint for t in totals), at, at, test_identity
    )
    return path, totals, evaluation


def point_scenario(repo: CostResearchRepository, fixture: CostFixture) -> CostScenario:
    sources = native_forecasts(repo, fixture.upstream.upstream, probability=False)
    return replace(fixture.scenario, scenario_id="supplied-point", source_ids=sources)


def test_spec_sources(repo: CostResearchRepository, fixture: CostFixture) -> tuple[str, ...]:
    return native_forecasts(repo, fixture.upstream.upstream, partition=Partition.TEST)


def component_variant(
    base: CostScenario, component: CostComponentSpec, tag: str, *, fixed: bool = False
) -> CostScenario:
    old = next(c for c in base.components if c.name == component.name)
    return replace(
        base,
        scenario_id=tag,
        components=tuple(component if c == old else c for c in base.components),
        bindings=tuple(
            replace(
                b, component_id=component.fingerprint, input_ids=() if fixed else b.input_ids
            )
            if b.component_id == old.fingerprint
            else b
            for b in base.bindings
        ),
    )
