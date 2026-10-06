"""Closed native forecast projection, exact sample identity and source quality evidence."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibratedForecast, IntervalValue
from afre.event_conditioned.artifacts import (
    EventConditionedForecast,
    EventConditionedObservation,
)
from afre.feature_store.materialization import PointInTimeJoinResult
from afre.forecast import ForecastOrigin
from afre.mixture.artifacts import MixtureDistribution, MixtureForecast
from afre.nonlinear.artifacts import NonlinearForecast
from afre.probabilistic.artifacts import DistributionParameters, ProbabilisticForecast
from afre.probabilistic.distributions import expected_value
from afre.regime_conditioned.artifacts import RegimeConditionedForecast, RegimeConditionedSample
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require
from afre.sequence.artifacts import SequenceForecast, SequenceSnapshot
from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec
from afre.target_engine.definitions import TargetDefinition

if TYPE_CHECKING:
    from afre.uncertainty.repository import UncertaintyRepository

Law = DistributionParameters | MixtureDistribution


@dataclass(frozen=True)
class ForecastSource:
    artifact: Artifact
    origin: ForecastOrigin
    target: TargetDefinition
    sample_id: str
    fold_id: str
    partition: Partition
    prediction: float
    law: Law | None
    model_id: str
    quality: tuple[str, ...]
    interval: IntervalValue | None
    available_ns: int


def source_for(repo: "UncertaintyRepository", identity: str) -> ForecastSource:
    value = repo.get_any(identity)
    require(
        isinstance(
            value,
            (
                PointForecast,
                ProbabilisticForecast,
                CalibratedForecast,
                EventConditionedForecast,
                RegimeConditionedForecast,
                MixtureForecast,
                NonlinearForecast,
                SequenceForecast,
            ),
        ),
        "unsupported uncertainty forecast source",
    )
    assert isinstance(
        value,
        (
            PointForecast,
            ProbabilisticForecast,
            CalibratedForecast,
            EventConditionedForecast,
            RegimeConditionedForecast,
            MixtureForecast,
            NonlinearForecast,
            SequenceForecast,
        ),
    )
    repo._validate_links(value)
    quality = {"source:" + type(value).__name__}
    law: Law | None = None
    interval = None
    if isinstance(value, (ProbabilisticForecast, CalibratedForecast)):
        point = (
            repo.resolve(PointForecast, value.point_forecast_id)
            if isinstance(value, ProbabilisticForecast)
            else repo.resolve(
                PointForecast,
                repo.resolve(ProbabilisticForecast, value.raw_forecast_id).point_forecast_id,
            )
        )
        origin, sample_id, model_id = (
            value.input.origin,
            value.input.sample_id,
            point.model_artifact_id,
        )
        if isinstance(value, ProbabilisticForecast):
            law = value.distribution
        else:
            interval = value.calibrated_interval
            quality.add(
                "calibration:"
                + ("full-law" if value.full_distribution_preserved else "marginals-only")
            )
            if value.full_distribution_preserved:
                law = repo.resolve(ProbabilisticForecast, value.raw_forecast_id).distribution
        prediction = expected_value(law) if isinstance(law, DistributionParameters) else None
        prediction = point.value if prediction is None else prediction
    elif isinstance(value, PointForecast):
        origin, sample_id, model_id, prediction = (
            value.input.origin,
            value.input.sample_id,
            value.model_artifact_id,
            value.value,
        )
        join = repo.resolve(PointInTimeJoinResult, value.input.join_id)
        quality.update("feature:" + a.state.value for a in join.audits)
    elif isinstance(value, (SequenceForecast, NonlinearForecast)):
        origin, sample_id, model_id, prediction = (
            value.origin,
            value.sample_id,
            value.model_id,
            value.value,
        )
        law = value.probability.distribution if value.probability else None
        if isinstance(value, SequenceForecast):
            snapshot = repo.resolve(SequenceSnapshot, value.snapshot_id)
            quality.add("sequence:" + snapshot.completeness.value)
            quality.update("sequence-exclusion:" + r for _, r in snapshot.exclusions)
        else:
            quality.add("nonlinear:" + ("tree" if value.path else "linear-readout"))
    elif isinstance(value, MixtureForecast):
        origin, sample_id = value.origin, value.request.sample_id
        model_id, prediction, law = value.request.gate_id, value.value, value.distribution
        quality.update("expert:" + c.reason for c in value.contributions)
        quality.add(
            "expert-available:" + str(sum(c.value is not None for c in value.contributions))
        )
    else:
        assert isinstance(value, (EventConditionedForecast, RegimeConditionedForecast))
        origin, model_id, prediction, law = (
            value.origin,
            value.model_id,
            value.value,
            value.distribution,
        )
        observation = (
            repo.resolve(EventConditionedObservation, value.observation_id)
            if isinstance(value, EventConditionedForecast)
            else repo.resolve(RegimeConditionedSample, value.observation_id)
        )
        sample_id = observation.sample_id
        quality.add("conditioning:" + value.state)
    bounds = repo.uncertainty_bounds
    from afre.serialization import canonical_json

    require(
        len(canonical_json(value).encode()) <= bounds.serialized_bytes,
        "uncertainty source payload bound",
    )
    if isinstance(law, DistributionParameters):
        require(len(law.samples) <= bounds.samples, "uncertainty empirical atom bound")
    elif isinstance(law, MixtureDistribution):
        require(
            len(law.components) <= bounds.experts
            and sum(len(c.distribution.samples) or 1 for c in law.components) <= bounds.samples,
            "uncertainty mixture expert/atom bound",
        )
    if isinstance(value, MixtureForecast):
        require(len(value.contributions) <= bounds.experts, "uncertainty expert count bound")
    require(sample_id is not None, "uncertainty requires an exact research sample")
    assert sample_id is not None
    sample = repo.resolve(ResearchSample, sample_id)
    target = repo.resolve(TargetDefinition, value.target_definition_id)
    require(
        sample.origin == origin and sample.target_definition_id == target.fingerprint,
        "uncertainty exact source/sample/target",
    )
    if isinstance(value, (SequenceForecast, NonlinearForecast)):
        from afre.nonlinear.definitions import NonlinearModelSpec
        from afre.sequence.definitions import SequenceModelSpec

        spec = (
            repo.resolve(SequenceModelSpec, value.spec_id)
            if isinstance(value, SequenceForecast)
            else repo.resolve(NonlinearModelSpec, value.spec_id)
        )
        fold_id = spec.fold_id
    elif isinstance(value, MixtureForecast):
        fold_id = value.request.fold_id
    else:
        if isinstance(value, (EventConditionedForecast, RegimeConditionedForecast)):
            base = repo.get_any(value.base_forecast_id)
            if isinstance(base, EventConditionedForecast):
                base = repo.resolve(PointForecast, base.base_forecast_id)
            require(isinstance(base, PointForecast), "conditioned exact point base")
            assert isinstance(base, PointForecast)
            point = base
        elif isinstance(value, PointForecast):
            point = value
        model = repo.resolve(FittedModelArtifact, point.model_artifact_id)
        fold_id = repo.resolve(BaselineModelSpec, model.spec_id).fold_id
    memberships = tuple(m for m in repo.fold_memberships(fold_id) if m.sample_id == sample_id)
    require(
        len(memberships) == 1
        and memberships[0].partition in (Partition.VALIDATION, Partition.TEST),
        "uncertainty cannot construct from TRAIN/TEST fitting diagnostics",
    )
    require(
        origin.timestamp_ns <= value.available_ns <= origin.availability_cutoff_ns,
        "source forecast unavailable at historical origin",
    )
    if hasattr(value, "historical_admissible"):
        require(value.historical_admissible, "noncausal forecast cannot carry uncertainty")
    return ForecastSource(
        value,
        origin,
        target,
        sample_id,
        fold_id,
        memberships[0].partition,
        prediction,
        law,
        model_id,
        tuple(sorted(quality)),
        interval,
        value.available_ns,
    )


def matched_alternatives(
    repo: "UncertaintyRepository", source: ForecastSource, ids: tuple[str, ...]
) -> tuple[ForecastSource, ...]:
    require(len(ids) <= repo.uncertainty_bounds.experts, "alternative model count bound")
    values = tuple(source_for(repo, i) for i in sorted(ids))
    require(
        all(
            s.origin == source.origin
            and s.sample_id == source.sample_id
            and s.target == source.target
            and s.fold_id == source.fold_id
            and s.partition is source.partition
            for s in values
        ),
        "alternative forecasts require exact matched origin/sample/target/fold",
    )
    require(
        len({s.model_id for s in values}) == len(values), "alternative models must be distinct"
    )
    return values
