"""Closed native AFRE-5..18 metadata projection, without access to later truth."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibratedForecast
from afre.costs.definitions import CostScenario
from afre.cross_sectional.artifacts import CrossSectionObservation, CrossSectionRanking
from afre.cross_sectional.definitions import CrossSectionSpec
from afre.event_conditioned.artifacts import EventConditionedForecast
from afre.forecast import ForecastOrigin
from afre.invariance.artifacts import EnvironmentMembership
from afre.invariance.definitions import EnvironmentSet, StabilityAnalysisSpec
from afre.mixture.artifacts import MixtureForecast
from afre.multihorizon.horizon_sets import HorizonSet
from afre.multiple_testing.hypotheses import HypothesisDefinition
from afre.multiple_testing.schema import AdaptiveTrialStatus, ResearchMetric
from afre.multiple_testing.trials import TrialSpecification
from afre.nonlinear.artifacts import NonlinearForecast
from afre.orthogonalization.artifacts import OrthogonalSignalValue, ProjectionArtifact
from afre.orthogonalization.definitions import OrthogonalizationSpec
from afre.orthogonalization.source_policy import producer_key
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.regime_conditioned.artifacts import RegimeConditionedForecast
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import FoldDefinition
from afre.schema import require
from afre.sequence.artifacts import SequenceForecast
from afre.statistical_models.artifacts import PointForecast
from afre.target_engine.definitions import TargetDefinition
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition
from afre.uncertainty.sources import source_for

if TYPE_CHECKING:
    from afre.multiple_testing.repository import MultipleTestingRepository


@dataclass(frozen=True)
class NativeTrialSource:
    identity: str
    sample_id: str
    origin: ForecastOrigin
    prediction: float
    unit: str
    producer: tuple[str, ...]


def project(
    repo: "MultipleTestingRepository",
    identity: str,
    hypothesis: HypothesisDefinition,
    fold_id: str,
) -> NativeTrialSource:
    value = repo.get_any(identity)
    if isinstance(value, OrthogonalSignalValue):
        projection = repo.resolve(ProjectionArtifact, value.projection_id)
        spec = repo.resolve(OrthogonalizationSpec, projection.spec_id)
        require(
            spec.target.fingerprint == hypothesis.target_id
            and spec.fold_id == fold_id
            and value.residual is not None
            and hypothesis.metric
            in (ResearchMetric.RESIDUAL_VALUE, ResearchMetric.NET_CONTRIBUTION),
            "exact available residual trial source/unit",
        )
        assert value.residual is not None
        return NativeTrialSource(
            identity,
            value.sample_id,
            value.origin,
            value.residual,
            value.unit
            if hypothesis.metric is ResearchMetric.RESIDUAL_VALUE
            else hypothesis.unit,
            (projection.fingerprint,),
        )
    require(
        hypothesis.metric is not ResearchMetric.RESIDUAL_VALUE,
        "residual metric requires an actual native residual source",
    )
    source = source_for(repo, identity)
    require(
        source.target.fingerprint == hypothesis.target_id
        and source.target.horizon.fingerprint == hypothesis.horizon_id
        and source.fold_id == fold_id,
        "exact native trial target/horizon/fold",
    )
    return NativeTrialSource(
        identity,
        source.sample_id,
        source.origin,
        source.prediction,
        hypothesis.unit,
        producer_key(repo, identity),
    )


def source_grid(
    repo: "MultipleTestingRepository", plan: TrialSpecification, right: bool = False
) -> tuple[NativeTrialSource, ...]:
    hypothesis = repo.resolve(HypothesisDefinition, plan.hypothesis_id)
    values = tuple(
        project(repo, i, hypothesis, plan.fold_id)
        for i in (plan.right_source_ids if right else plan.source_ids)
    )
    require(
        len({v.sample_id for v in values}) == len(values)
        and len({v.producer for v in values}) <= 1
        and len({type(repo.get_any(v.identity)) for v in values}) <= 1,
        "one frozen producer per trial side/sample",
    )
    return tuple(sorted(values, key=lambda v: v.sample_id))


def validate_plan(repo: "MultipleTestingRepository", plan: TrialSpecification) -> None:
    h = repo.resolve(HypothesisDefinition, plan.hypothesis_id)
    fold = repo.resolve(FoldDefinition, plan.fold_id)
    target = repo.resolve(TargetDefinition, h.target_id)
    require(
        target.horizon.fingerprint == h.horizon_id
        and fold.dataset_id == plan.dataset_id
        and h.declared_ns <= plan.declared_ns,
        "trial target/horizon/dataset/declaration",
    )
    left, right = source_grid(repo, plan), source_grid(repo, plan, True)
    require(
        {v.sample_id for v in left} == set(plan.sample_ids),
        "exact declared left-side sample grid",
    )
    parts = {m.sample_id: m.partition for m in repo.fold_memberships(plan.fold_id)}
    require(
        all(
            not repo.resolve(ResearchSample, v.sample_id).dropped
            and parts.get(v.sample_id) in (Partition.VALIDATION, Partition.TEST)
            for v in (*left, *right)
        ),
        "only admitted held-out trial samples",
    )
    require(
        all(
            v.origin == repo.resolve(ResearchSample, v.sample_id).origin
            for v in (*left, *right)
        ),
        "exact source/sample origin",
    )
    require(
        plan.adaptivity is not AdaptiveTrialStatus.PREDECLARED
        or plan.declared_ns <= fold.training_cutoff_ns,
        "claimed predeclaration before held-out boundary",
    )
    for identity in plan.known_trial_ids:
        row = repo._connection.execute(
            "SELECT kind,available_ns FROM mt_records WHERE fingerprint=?", (identity,)
        ).fetchone()
        require(
            row is not None and row[0] == "ResearchTrial" and row[1] <= plan.declared_ns,
            "adaptive parent result known by declaration",
        )
    for identity in (*plan.preprocessing_ids, *plan.model_spec_ids):
        repo.get_any(identity)
    native = repo.get_any(plan.source_artifact_id)
    forecast_classes = {
        5: PointForecast,
        6: ProbabilisticForecast,
        7: CalibratedForecast,
        10: EventConditionedForecast,
        11: RegimeConditionedForecast,
        12: MixtureForecast,
        13: NonlinearForecast,
        14: SequenceForecast,
        16: OrthogonalSignalValue,
    }
    if plan.native_phase in forecast_classes:
        require(
            type(native) is forecast_classes[plan.native_phase]
            and native.fingerprint in plan.source_ids,
            "native phase source class/prototype",
        )
    elif plan.native_phase == 8:
        require(
            isinstance(native, HorizonSet) and target in native.targets,
            "native AFRE-8 exact horizon set",
        )
    elif plan.native_phase == 9:
        require(isinstance(native, CrossSectionRanking), "native AFRE-9 ranking required")
        assert isinstance(native, CrossSectionRanking)
        spec = repo.resolve(CrossSectionSpec, native.spec_id)
        require(
            spec.identity.target == target
            and {
                repo.resolve(CrossSectionObservation, e.observation_id).source_id
                for e in native.entries
                if e.rank is not None
            }
            <= set(plan.source_ids),
            "ranking exact target/underlying sources",
        )
    elif plan.native_phase == 15:
        require(
            isinstance(native, ForecastUncertaintyDecomposition),
            "native AFRE-15 decomposition required",
        )
        assert isinstance(native, ForecastUncertaintyDecomposition)
        require(
            native.forecast_id in plan.source_ids
            and native.target_id == h.target_id
            and native.fold_id == plan.fold_id,
            "uncertainty exact trial source",
        )
    elif plan.native_phase == 17:
        require(
            isinstance(native, StabilityAnalysisSpec),
            "native AFRE-17 analysis specification required",
        )
        assert isinstance(native, StabilityAnalysisSpec)
        envs = repo.resolve(EnvironmentSet, native.environment_set_id)
        require(
            plan.environment_id in {d.fingerprint for d in envs.definitions}
            and set(plan.source_ids) <= set(native.forecast_ids)
            and native.target == target
            and native.fold_id == plan.fold_id,
            "environment trial exact supplied analysis",
        )
    else:
        require(
            isinstance(native, CostScenario) and plan.cost_scenario_id == native.fingerprint,
            "native AFRE-18 scenario required",
        )
    if plan.cost_scenario_id:
        scenario = repo.resolve(CostScenario, plan.cost_scenario_id)
        require(
            scenario.target == target
            and scenario.fold_id == plan.fold_id
            and scenario.source_ids == plan.source_ids
            and scenario.sample_ids == plan.sample_ids,
            "cost trial exact scenario choices/sources",
        )
    require(
        (h.metric is ResearchMetric.NET_CONTRIBUTION) == (plan.cost_scenario_id is not None),
        "net research metric requires exact cost scenario",
    )
    if plan.environment_id:
        members = tuple(repo.resolve(EnvironmentMembership, i) for i in plan.membership_ids)
        require(
            {m.sample_id for m in members} == set(plan.sample_ids)
            and len(members) == len(plan.sample_ids)
            and all(m.environment_id == plan.environment_id for m in members),
            "one exact native environment membership per declared sample",
        )
