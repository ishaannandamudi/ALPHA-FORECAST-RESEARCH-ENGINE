"""Causal frozen forecasts or AFRE-16 residual values on exact admitted research samples."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.costs.definitions import CostScenario
from afre.forecast import ForecastOrigin
from afre.orthogonalization.artifacts import OrthogonalSignalValue, ProjectionArtifact
from afre.orthogonalization.definitions import OrthogonalizationSpec
from afre.orthogonalization.schema import OrthogonalQuality
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import FoldDefinition
from afre.schema import require
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition
from afre.uncertainty.sources import source_for

if TYPE_CHECKING:
    from afre.costs.repository import CostResearchRepository


@dataclass(frozen=True)
class ResearchCostSource:
    identity: str
    sample_id: str
    origin: ForecastOrigin
    value: float
    available_ns: int
    producer: str


def sources_for(
    repo: "CostResearchRepository", scenario: CostScenario
) -> tuple[ResearchCostSource, ...]:
    fold = repo.resolve(FoldDefinition, scenario.fold_id)
    require(
        scenario.declared_ns <= fold.training_cutoff_ns,
        "cost settings must precede held-out assessment/TRAIN cutoff",
    )
    require(
        repo.get_any(scenario.target.fingerprint) == scenario.target,
        "cost exact target definition",
    )
    partitions = {m.sample_id: m.partition for m in repo.fold_memberships(scenario.fold_id)}
    values: list[ResearchCostSource] = []
    for identity in scenario.source_ids:
        value = repo.get_any(identity)
        from afre.fusion.artifacts import FusedForecast

        if isinstance(value, FusedForecast):
            require(
                value.value is not None
                and value.target_id == scenario.target.fingerprint
                and value.horizon_id == scenario.target.horizon.fingerprint
                and value.fold_id == scenario.fold_id
                and value.unit == "target-value:" + scenario.target.fingerprint
                and scenario.signal_unit == "return_fraction",
                "exact causal fused cost forecast",
            )
            assert value.value is not None
            s = ResearchCostSource(
                identity,
                value.sample_id,
                value.origin,
                value.value,
                value.available_ns,
                value.artifact_id,
            )
        elif isinstance(value, OrthogonalSignalValue):
            repo._validate_links(value)
            p = repo.resolve(ProjectionArtifact, value.projection_id)
            spec = repo.resolve(OrthogonalizationSpec, p.spec_id)
            require(
                spec.target == scenario.target
                and spec.fold_id == scenario.fold_id
                and value.quality is OrthogonalQuality.AVAILABLE
                and value.residual is not None
                and value.available_ns <= value.origin.availability_cutoff_ns,
                "causal residual cost source",
            )
            require(value.unit == scenario.signal_unit, "residual signal threshold units")
            assert value.residual is not None
            s = ResearchCostSource(
                identity,
                value.sample_id,
                value.origin,
                value.residual,
                value.available_ns,
                p.fingerprint,
            )
        else:
            f = source_for(repo, identity)
            require(scenario.signal_unit == "return_fraction", "forecast threshold units")
            require(
                f.target == scenario.target and f.fold_id == scenario.fold_id,
                "cost source exact fold/target/horizon",
            )
            s = ResearchCostSource(
                identity, f.sample_id, f.origin, f.prediction, f.available_ns, f.model_id
            )
        sample = repo.resolve(ResearchSample, s.sample_id)
        require(
            sample.origin == s.origin
            and sample.target_definition_id == scenario.target.fingerprint
            and not sample.dropped
            and partitions.get(s.sample_id) in (Partition.VALIDATION, Partition.TEST),
            "cost exact admitted held-out sample",
        )
        values.append(s)
    require(
        {s.sample_id for s in values} == set(scenario.sample_ids)
        and len(values) == len(scenario.sample_ids),
        "one exact causal source per cost sample",
    )
    require(
        len({(type(repo.get_any(s.identity)), s.producer) for s in values}) == 1,
        "cost scenario requires one frozen supplied signal producer",
    )
    return tuple(
        sorted(
            values,
            key=lambda s: (s.origin.instrument.fingerprint, s.origin.timestamp_ns, s.sample_id),
        )
    )


def validate_uncertainty(repo: "CostResearchRepository", scenario: CostScenario) -> None:
    samples = set()
    for identity in scenario.uncertainty_ids:
        u = repo.resolve(ForecastUncertaintyDecomposition, identity)
        require(
            u.forecast_id in scenario.source_ids
            and u.sample_id in scenario.sample_ids
            and u.fold_id == scenario.fold_id
            and u.target_id == scenario.target.fingerprint
            and u.horizon_id == scenario.target.horizon.fingerprint,
            "uncertainty attachment exact source/sample/target",
        )
        require(u.sample_id not in samples, "one uncertainty attachment per cost sample")
        samples.add(u.sample_id)
