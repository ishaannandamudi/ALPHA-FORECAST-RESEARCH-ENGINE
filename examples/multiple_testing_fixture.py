"""Bounded offline AFRE5..18 opportunities with exact native source identities."""

from dataclasses import dataclass, replace

from afre.costs import CostResearchEngine
from afre.cross_sectional import CrossSectionEngine
from afre.invariance import EnvironmentMembership, StabilityAnalysisSpec
from afre.multihorizon import HorizonSet
from afre.multiple_testing import (
    AdaptiveTrialStatus,
    CorrectionMethod,
    DependenceAssumption,
    HypothesisDefinition,
    HypothesisDirection,
    HypothesisFamily,
    MultipleTestingEngine,
    MultipleTestingRepository,
    RawTestMethod,
    ResearchMetric,
    TestAssumptions,
    TrialSpecification,
)
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.target_engine.definitions import TargetDefinition
from afre.uncertainty.sources import source_for
from examples.costs_fixture import CostFixture
from examples.costs_fixture import build_fixture as native_fixture
from examples.costs_workflow import assess, component_variant
from examples.cross_sectional_demo import spec_for
from examples.invariance_fixture import native_forecasts
from examples.invariance_horizons import horizon_analyses


@dataclass(frozen=True)
class TestingFixture:
    native: CostFixture
    family: HypothesisFamily
    plans: tuple[TrialSpecification, ...]
    cost_results: tuple[tuple[str, str], ...]
    cutoffs: tuple[tuple[str, int], ...]

    def plan(self, key: str) -> TrialSpecification:
        return next(p for p in self.plans if p.attempt_key == key)


def declare_plan(
    repo: MultipleTestingRepository,
    key: str,
    family_key: str,
    phase: int,
    prototype: str,
    sources: tuple[str, ...],
    *,
    metric: ResearchMetric = ResearchMetric.FORECAST_ERROR,
    method: RawTestMethod = RawTestMethod.EXACT_SIGN,
    right: tuple[str, ...] = (),
    environment: str | None = None,
    members: tuple[str, ...] = (),
    cost: str | None = None,
    declared: int = 40,
    adaptivity: AdaptiveTrialStatus = AdaptiveTrialStatus.PREDECLARED,
    known: tuple[str, ...] = (),
    null: float = 0.0,
) -> TrialSpecification:
    engine = MultipleTestingEngine(repo)
    first = source_for(repo, sources[0]) if phase != 16 else None
    if first is None:
        from afre.orthogonalization import OrthogonalSignalValue, ProjectionArtifact
        from afre.orthogonalization.definitions import OrthogonalizationSpec

        value = repo.resolve(OrthogonalSignalValue, sources[0])
        projection = repo.resolve(ProjectionArtifact, value.projection_id)
        spec = repo.resolve(OrthogonalizationSpec, projection.spec_id)
        target, fold_id = spec.target, spec.fold_id
        samples = tuple(repo.resolve(OrthogonalSignalValue, i).sample_id for i in sources)
    else:
        target, fold_id = first.target, first.fold_id
        samples = tuple(source_for(repo, i).sample_id for i in sources)
    from afre.research_datasets.splits import FoldDefinition

    fold = repo.resolve(FoldDefinition, fold_id)
    h = engine.hypothesis(
        HypothesisDefinition(
            key,
            family_key,
            target.fingerprint,
            target.horizon.fingerprint,
            metric,
            null,
            HypothesisDirection.TWO_SIDED,
            method,
            2,
            TestAssumptions(
                True, True, bool(right), True, "offline-explicit-assumptions", declared
            ),
            declared,
        )
    )
    return engine.plan(
        TrialSpecification(
            key,
            h.fingerprint,
            phase,
            prototype,
            sources,
            samples,
            fold.dataset_id,
            fold_id,
            (),
            (),
            (("inspected-alternative", key),),
            declared,
            adaptivity,
            known_trial_ids=known,
            right_source_ids=right,
            environment_id=environment,
            membership_ids=members,
            cost_scenario_id=cost,
        )
    )


def declare_fixture(
    repo: MultipleTestingRepository,
    native: CostFixture,
    reverse: bool = False,
    *,
    horizons: bool = True,
) -> TestingFixture:
    engine = MultipleTestingEngine(repo)
    orth = native.upstream.upstream
    uncertainty = orth.upstream
    plans: list[TrialSpecification] = []
    cutoffs: list[tuple[str, int]] = []
    results: list[tuple[str, str]] = []
    family_key = "offline-all-declared-opportunities"
    streams = (
        (5, "point"),
        (6, "gaussian"),
        (7, "calibrated"),
        (10, "event"),
        (11, "hard-regime"),
        (12, "mixture"),
        (13, "nonlinear"),
        (14, "sequence"),
    )
    for phase, name in reversed(streams) if reverse else streams:
        ids = uncertainty.ids(name)
        plans.append(declare_plan(repo, f"phase-{phase}", family_key, phase, min(ids), ids))
    horizon_set = HorizonSet((native.scenario.target,))
    with repo.transaction():
        repo.put(horizon_set)
    ids = uncertainty.ids("point")
    plans.append(declare_plan(repo, "phase-8", family_key, 8, horizon_set.fingerprint, ids))
    probabilities = tuple(
        repo.resolve(ProbabilisticForecast, i) for i in uncertainty.ids("gaussian")
    )
    ranking = CrossSectionEngine(repo).build_ranking(
        spec_for(repo, probabilities, False),
        tuple(
            (
                repo.resolve(ResearchSample, p.input.sample_id or "").security.fingerprint,
                p.point_forecast_id,
            )
            for p in probabilities
        ),
    )
    plans.append(
        declare_plan(
            repo,
            "phase-9",
            family_key,
            9,
            ranking.fingerprint,
            tuple(p.point_forecast_id for p in probabilities),
        )
    )
    ids = uncertainty.ids("gaussian")
    plans.append(
        declare_plan(
            repo, "phase-15", family_key, 15, min(uncertainty.results("gaussian")), ids
        )
    )
    ids = orth.residual_ids(Partition.VALIDATION)
    plans.append(
        declare_plan(
            repo,
            "phase-16",
            family_key,
            16,
            min(ids),
            ids,
            metric=ResearchMetric.RESIDUAL_VALUE,
        )
    )
    for definition in (
        reversed(native.upstream.environment_set.definitions)
        if reverse
        else native.upstream.environment_set.definitions
    ):
        members = tuple(
            i
            for i in native.upstream.membership_ids
            if repo.resolve(EnvironmentMembership, i).environment_id == definition.fingerprint
        )
        plans.append(
            declare_plan(
                repo,
                "env-" + definition.environment_id,
                family_key,
                17,
                native.upstream.spec.fingerprint,
                native.upstream.spec.forecast_ids,
                environment=definition.fingerprint,
                members=members,
            )
        )
    fee = next(c for c in native.scenario.components if c.name == "fee")
    alternate = component_variant(
        native.scenario, replace(fee, fixed_value=0.03), "higher-fee", fixed=True
    )
    scenarios = (native.scenario, alternate)
    for j, scenario in (
        reversed(tuple(enumerate(scenarios))) if reverse else enumerate(scenarios)
    ):
        evaluation = assess(CostResearchEngine(repo), scenario)[2]
        p = declare_plan(
            repo,
            f"cost-{j}",
            family_key,
            18,
            scenario.fingerprint,
            scenario.source_ids,
            metric=ResearchMetric.NET_CONTRIBUTION,
            cost=scenario.fingerprint,
        )
        plans.append(p)
        results.append((p.fingerprint, evaluation.fingerprint))
    for name, method in (
        ("unsupported", RawTestMethod.NORMAL_MEAN),
        ("failed", RawTestMethod.EXACT_SIGN),
        ("unavailable", RawTestMethod.EXACT_SIGN),
    ):
        ids = uncertainty.ids("point")
        plans.append(declare_plan(repo, name, family_key, 5, min(ids), ids, method=method))
    left, right = uncertainty.ids("point"), uncertainty.ids("gaussian")
    plans.append(
        declare_plan(
            repo,
            "paired",
            family_key,
            5,
            min(left),
            left,
            method=RawTestMethod.EXACT_PAIRED_SIGN,
            right=right,
        )
    )
    ids = native_forecasts(repo, orth, probability=False, partition=Partition.TEST)
    for j in reversed(range(3)) if reverse else range(3):
        plans.append(declare_plan(repo, f"test-{j}", family_key, 5, min(ids), ids))
    if horizons:
        metrics = horizon_analyses(repo)
        for value in reversed(metrics) if reverse else metrics:
            spec = repo.resolve(StabilityAnalysisSpec, value.spec_id)
            target: TargetDefinition = spec.target
            hs = HorizonSet((target,))
            with repo.transaction():
                repo.put(hs)
            p = declare_plan(
                repo,
                "actual-" + str(target.horizon.duration_ns),
                family_key,
                8,
                hs.fingerprint,
                spec.forecast_ids,
            )
            plans.append(p)
            cutoffs.append((p.fingerprint, value.available_ns))
    family = engine.family(
        HypothesisFamily(
            family_key,
            tuple(p.fingerprint for p in reversed(plans) if reverse)
            if reverse
            else tuple(p.fingerprint for p in plans),
            CorrectionMethod.HOLM,
            0.05,
            DependenceAssumption.PRDS,
            40,
            True,
            (
                CorrectionMethod.BONFERRONI,
                CorrectionMethod.BENJAMINI_HOCHBERG,
                CorrectionMethod.BENJAMINI_YEKUTIELI,
            ),
        )
    )
    return TestingFixture(
        native,
        family,
        tuple(sorted(plans, key=lambda p: p.attempt_key)),
        tuple(sorted(results)),
        tuple(sorted(cutoffs)),
    )


def build_fixture(repo: MultipleTestingRepository, reverse: bool = False) -> TestingFixture:
    return declare_fixture(repo, native_fixture(repo, reverse), reverse)
