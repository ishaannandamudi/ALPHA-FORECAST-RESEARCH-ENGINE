"""Native frozen forecast projection; TRAIN is later in-sample description only."""

from typing import TYPE_CHECKING

from afre.feature_store.materialization import PointInTimeJoinResult
from afre.invariance.definitions import EnvironmentSet, StabilityAnalysisSpec
from afre.orthogonalization.source_policy import producer_key
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import FoldDefinition
from afre.schema import require
from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.schema import PredictionScope
from afre.uncertainty.sources import ForecastSource, source_for

if TYPE_CHECKING:
    from afre.invariance.repository import InvarianceRepository


def forecast_source(repo: "InvarianceRepository", identity: str) -> ForecastSource:
    value = repo.get_any(identity)
    if (
        not isinstance(value, PointForecast)
        or value.input.scope is not PredictionScope.IN_SAMPLE
    ):
        return source_for(repo, identity)
    repo._validate_links(value)
    require(
        not value.historical_admissible and value.input.sample_id is not None,
        "TRAIN is explicit later in-sample",
    )
    assert value.input.sample_id is not None
    sample = repo.resolve(ResearchSample, value.input.sample_id)
    model = repo.resolve(FittedModelArtifact, value.model_artifact_id)
    spec = repo.resolve(BaselineModelSpec, model.spec_id)
    require(
        sample.origin == value.input.origin
        and sample.target_definition_id == spec.target.fingerprint
        and any(
            m.sample_id == sample.fingerprint and m.partition is Partition.TRAIN
            for m in repo.fold_memberships(spec.fold_id)
        ),
        "in-sample exact TRAIN sample",
    )
    join = repo.resolve(PointInTimeJoinResult, value.input.join_id)
    return ForecastSource(
        value,
        value.input.origin,
        spec.target,
        sample.fingerprint,
        spec.fold_id,
        Partition.TRAIN,
        value.value,
        None,
        model.fingerprint,
        tuple(
            sorted(
                {"scope:later-in-sample", *("feature:" + a.state.value for a in join.audits)}
            )
        ),
        None,
        value.available_ns,
    )


def validate_spec(repo: "InvarianceRepository", spec: StabilityAnalysisSpec) -> None:
    b = repo.invariance_bounds
    require(
        len(spec.sample_ids) <= b.samples
        and len(spec.forecast_ids) <= b.forecasts
        and len(spec.uncertainty_ids) <= b.forecasts
        and len(spec.metrics) <= b.metrics
        and len(spec.feature_reference_ids) <= b.features,
        "analysis repository bounds",
    )
    envs = repo.resolve(EnvironmentSet, spec.environment_set_id)
    fold = repo.resolve(FoldDefinition, spec.fold_id)
    require(
        envs.declared_ns <= spec.declared_ns <= fold.training_cutoff_ns
        and envs.definitions[0].target == spec.target,
        "environments/settings predeclared before held-out evidence",
    )
    require(
        spec.baseline_environment_id is None
        or spec.baseline_environment_id in {d.fingerprint for d in envs.definitions},
        "predeclared baseline in set",
    )
    memberships = {m.sample_id: m.partition for m in repo.fold_memberships(spec.fold_id)}
    for identity in spec.sample_ids:
        s = repo.resolve(ResearchSample, identity)
        require(
            s.target_definition_id == spec.target.fingerprint
            and not s.dropped
            and memberships.get(identity)
            in (Partition.TRAIN, Partition.VALIDATION, Partition.TEST),
            "analysis admitted exact fold/target samples",
        )
    from afre.orthogonalization.definitions import SignalReference

    for identity in spec.feature_reference_ids:
        reference = repo.resolve(SignalReference, identity)
        require(
            reference.target is None or reference.target == spec.target,
            "declared shift feature target/horizon",
        )
    from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition

    uncertainty = tuple(
        repo.resolve(ForecastUncertaintyDecomposition, i) for i in spec.uncertainty_ids
    )
    require(
        len({d.forecast_id for d in uncertainty}) == len(uncertainty)
        and all(
            d.forecast_id in spec.forecast_ids
            and d.sample_id in spec.sample_ids
            and d.fold_id == spec.fold_id
            and d.target_id == spec.target.fingerprint
            and d.horizon_id == spec.target.horizon.fingerprint
            for d in uncertainty
        ),
        "declared exact uncertainty source evidence",
    )
    sources = tuple(forecast_source(repo, i) for i in spec.forecast_ids)
    require(
        len({s.sample_id for s in sources}) == len(sources)
        and all(
            s.target == spec.target
            and s.fold_id == spec.fold_id
            and s.sample_id in spec.sample_ids
            for s in sources
        ),
        "single frozen forecast per exact sample/target/fold",
    )
    require(
        len({producer_key(repo, i) for i in spec.forecast_ids}) == 1
        and len({type(s.artifact) for s in sources}) == 1,
        "analysis frozen producer and calibration semantics",
    )
