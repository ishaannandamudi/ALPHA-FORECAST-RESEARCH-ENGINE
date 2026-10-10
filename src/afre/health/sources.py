"""Closed native projections; monitoring never fits or changes a producer."""

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from afre.costs.artifacts import (
    BreakEvenCostDiagnostic,
    CostAwareEvaluation,
    CostAwareSampleEvaluation,
)
from afre.costs.definitions import CostScenario
from afre.cross_sectional.artifacts import CrossSectionRanking
from afre.cross_sectional.definitions import CrossSectionSpec
from afre.fusion.artifacts import FusedForecast, FusionArtifact
from afre.fusion.definitions import FusionSpec
from afre.fusion.sources import FAMILIES
from afre.fusion.sources import reference_for as fusion_reference
from afre.health.artifacts import HealthObservation
from afre.health.definitions import MonitoredArtifactReference
from afre.invariance.artifacts import EnvironmentMetric
from afre.invariance.definitions import StabilityAnalysisSpec
from afre.orthogonalization.artifacts import OrthogonalSignalValue
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require
from afre.selection.results import SelectionResult
from afre.statistical_models.artifacts import FittedModelArtifact, ModelFitInputs
from afre.statistical_models.definitions import BaselineModelSpec
from afre.target_engine.definitions import TargetDefinition
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition
from afre.uncertainty.sources import source_for

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository


def reference_for(
    repo: "HealthRepository", identity: str, anchor_id: str | None = None
) -> MonitoredArtifactReference:
    spec: FusionSpec | BaselineModelSpec | StabilityAnalysisSpec | CrossSectionSpec
    raw = (
        repo.get(SelectionResult, identity)
        if identity.startswith("afre." + SelectionResult.domain + ":")
        else repo.get_any(identity)
    )
    if anchor_id is not None:
        anchor = reference_for(repo, anchor_id)
        require(identity == anchor.producer_id, "health model must produce exact anchor output")
        return replace(
            anchor,
            artifact_id=identity,
            artifact_type=type(raw).__name__,
            anchor_output_id=anchor_id,
        )
    if isinstance(raw, FusedForecast):
        spec = repo.resolve(FusionSpec, repo.resolve(FusionArtifact, raw.artifact_id).spec_id)
        return MonitoredArtifactReference(
            identity,
            type(raw).__name__,
            raw.artifact_id,
            raw.target_id,
            raw.horizon_id,
            raw.unit,
            "frozen-fusion:" + spec.kind.value,
            repo.get(FusionArtifact, raw.artifact_id).available_ns,
            raw.fold_id,
            spec.dataset_id,
        )
    if isinstance(raw, FusionArtifact):
        spec = repo.resolve(FusionSpec, raw.spec_id)
        return MonitoredArtifactReference(
            identity,
            type(raw).__name__,
            identity,
            spec.target_id,
            spec.horizon_id,
            spec.output_unit or spec.unit,
            "frozen-fusion:" + spec.kind.value,
            raw.available_ns,
            spec.fold_id,
            spec.dataset_id,
        )
    if type(raw).__name__ in FAMILIES or isinstance(raw, OrthogonalSignalValue):
        ref = fusion_reference(repo, identity)
        if isinstance(raw, OrthogonalSignalValue):
            from afre.orthogonalization.artifacts import ProjectionArtifact
            from afre.orthogonalization.definitions import OrthogonalizationSpec

            fold_id = repo.get(
                OrthogonalizationSpec, repo.get(ProjectionArtifact, raw.projection_id).spec_id
            ).fold_id
        else:
            fold_id = source_for(repo, identity).fold_id
        return MonitoredArtifactReference(
            identity,
            type(raw).__name__,
            ref.artifact_id,
            ref.target_id,
            ref.horizon_id,
            ref.unit,
            "native:" + ref.kind.value,
            ref.available_ns,
            fold_id,
        )
    if isinstance(raw, FittedModelArtifact):
        spec = repo.resolve(BaselineModelSpec, raw.spec_id)
        fit = repo.resolve(ModelFitInputs, raw.fit_inputs_id)
        return MonitoredArtifactReference(
            identity,
            type(raw).__name__,
            identity,
            spec.target.fingerprint,
            spec.target.horizon.fingerprint,
            "target-value:" + spec.target.fingerprint,
            "native:POINT",
            fit.model_available_ns,
            spec.fold_id,
            fit.dataset_id,
        )
    if isinstance(raw, ForecastUncertaintyDecomposition):
        base = reference_for(repo, raw.forecast_id)
        return replace(
            base,
            artifact_id=identity,
            artifact_type=type(raw).__name__,
            output_semantics="native-uncertainty",
            available_ns=raw.available_ns,
        )
    if isinstance(raw, EnvironmentMetric):
        spec = repo.resolve(StabilityAnalysisSpec, raw.spec_id)
        return MonitoredArtifactReference(
            identity,
            type(raw).__name__,
            raw.spec_id,
            spec.target.fingerprint,
            spec.target.horizon.fingerprint,
            "native-stability-metric",
            "native-stability-context",
            raw.available_ns,
            spec.fold_id,
        )
    if isinstance(raw, (CostAwareEvaluation, CostAwareSampleEvaluation)):
        scenario = repo.resolve(CostScenario, raw.scenario_id)
        return MonitoredArtifactReference(
            identity,
            type(raw).__name__,
            raw.scenario_id,
            scenario.target.fingerprint,
            scenario.target.horizon.fingerprint,
            "return-fraction",
            "native-cost-hypothetical",
            raw.available_ns,
            scenario.fold_id,
        )
    if isinstance(raw, BreakEvenCostDiagnostic):
        base = reference_for(repo, raw.evaluation_id)
        return replace(
            base,
            artifact_id=identity,
            artifact_type=type(raw).__name__,
            unit=raw.threshold_unit.value,
            available_ns=raw.available_ns,
        )
    if isinstance(raw, CrossSectionRanking):
        spec = repo.resolve(CrossSectionSpec, raw.spec_id)
        return MonitoredArtifactReference(
            identity,
            type(raw).__name__,
            raw.spec_id,
            spec.identity.target.fingerprint,
            spec.identity.target.horizon.fingerprint,
            "ordinal-rank",
            "native-cross-sectional-ranking",
            raw.available_ns,
        )
    require(
        isinstance(raw, SelectionResult) and raw.selected_model_id is not None,
        "unsupported monitored artifact or selection without model",
    )
    assert isinstance(raw, SelectionResult) and raw.selected_model_id is not None
    base = reference_for(repo, raw.selected_model_id)
    return replace(
        base,
        artifact_id=identity,
        artifact_type=type(raw).__name__,
        available_ns=raw.available_ns,
        output_semantics=base.output_semantics,
    )


def _parameter_values(
    repo: "HealthRepository", raw: Artifact
) -> tuple[tuple[str, float | None], ...]:
    from afre.health.parameters import parameter_values

    return parameter_values(repo, raw)


def observation_for(
    repo: "HealthRepository",
    ref: MonitoredArtifactReference,
    identity: str,
    constructed_ns: int,
) -> HealthObservation:
    raw = repo.get_any(identity)
    sample_id: str | None = None
    security_id: str | None = None
    partition: Partition | None = None
    quality: tuple[str, ...] = ("source:" + type(raw).__name__,)
    available = cast(int, getattr(raw, "available_ns", ref.available_ns))
    valid = available
    values: tuple[tuple[str, float | None], ...]
    if type(raw).__name__ in FAMILIES:
        source = source_for(repo, identity)
        actual = reference_for(repo, identity)
        require(actual.producer_id == ref.producer_id, "health exact frozen forecast producer")
        sample_id, valid, available, partition = (
            source.sample_id,
            source.origin.timestamp_ns,
            source.available_ns,
            source.partition,
        )
        security_id = source.origin.instrument.fingerprint
        quality = source.quality
        values = (("prediction", source.prediction),)
        if source.interval is not None:
            values += (("interval_width", source.interval.upper - source.interval.lower),)
        from afre.health.probabilities import predictive_variance

        values += (("predictive_variance", predictive_variance(source.law)),)
        from math import hypot

        from afre.sequence.artifacts import SequenceForecast
        from afre.sequence.definitions import SequenceModelSpec

        if isinstance(raw, SequenceForecast):
            sequence_spec = repo.get(SequenceModelSpec, raw.spec_id)
            values += tuple(
                ("aggregate:" + f.fingerprint, v)
                for f, v in zip(sequence_spec.features, raw.aggregates, strict=True)
            )
            values += (
                (
                    "state_norm",
                    hypot(*raw.state_trajectory[-1]) if raw.state_trajectory else None,
                ),
            )
    elif isinstance(raw, FusedForecast):
        require(
            raw.artifact_id == ref.producer_id and raw.unit == ref.unit,
            "health frozen fusion producer/unit",
        )
        sample_id, security_id, valid, partition = (
            raw.sample_id,
            raw.origin.instrument.fingerprint,
            raw.origin.timestamp_ns,
            raw.partition,
        )
        values = (
            ("prediction", raw.value),
            *(("contribution:" + c.source_id, c.weighted_value) for c in raw.contributions),
        )
        quality = ("fusion:" + raw.status.value,)
        from afre.health.probabilities import predictive_variance

        values += (("predictive_variance", predictive_variance(raw.law)),)
    elif isinstance(raw, OrthogonalSignalValue):
        require(raw.projection_id == ref.producer_id, "health frozen residual producer")
        sample_id, security_id, valid = (
            raw.sample_id,
            raw.origin.instrument.fingerprint,
            raw.origin.timestamp_ns,
        )
        from afre.orthogonalization.artifacts import AlignedSignalRow

        row = repo.resolve(AlignedSignalRow, raw.row_id)
        values = (
            ("prediction", raw.residual),
            ("raw", raw.raw_candidate),
            ("projection", raw.projected),
            *(("reference:" + str(j), v) for j, v in enumerate(row.references)),
        )
        quality = ("orthogonal:" + raw.quality.value,)
    elif isinstance(raw, ForecastUncertaintyDecomposition):
        require(
            reference_for(repo, raw.forecast_id).producer_id == ref.producer_id,
            "health frozen uncertainty producer",
        )
        sample_id, security_id, valid, partition = (
            raw.sample_id,
            raw.origin.instrument.fingerprint,
            raw.origin.timestamp_ns,
            raw.partition,
        )
        values = (
            ("total_variance", raw.total_variance),
            *(("share:" + k.value, v) for k, v in raw.shares),
            *(
                ("component:" + c.component.value + ":" + c.measure.value, c.value)
                for c in raw.components
            ),
        )
        quality = raw.quality_states
    elif isinstance(raw, CostAwareSampleEvaluation):
        require(raw.scenario_id == ref.producer_id, "health exact cost scenario")
        sample_id, security_id, valid = (
            raw.sample_id,
            raw.origin.instrument.fingerprint,
            raw.origin.timestamp_ns,
        )
        values = (
            ("gross", raw.gross_contribution),
            ("cost", raw.total_cost),
            ("net", raw.net_contribution),
        )
        from afre.costs.artifacts import ResearchExposureChange

        change = repo.resolve(ResearchExposureChange, raw.change_id)
        values += (("turnover", abs(change.trade_delta)),)
        quality = ("cost:" + raw.state.value, "truth-dependent-native-evaluation")
    elif isinstance(raw, CostAwareEvaluation):
        require(raw.scenario_id == ref.producer_id, "health exact cost aggregate")
        valid = raw.evaluation_cutoff_ns
        values = (
            ("gross", raw.gross_mean),
            ("cost", raw.mean_cost),
            ("net", raw.net_mean),
            ("turnover", raw.turnover),
        )
        quality = (
            "cost:" + raw.state.value,
            "truth-dependent-native-evaluation",
            "aggregate-cutoff-valid-time",
        )
    elif isinstance(raw, BreakEvenCostDiagnostic):
        require(identity == ref.artifact_id, "health exact break-even diagnostic")
        values = (("break_even", raw.threshold),)
        quality += ("truth-dependent-native-evaluation",)
    elif isinstance(raw, EnvironmentMetric):
        require(raw.spec_id == ref.producer_id, "health frozen stability context")
        values = (("metric", raw.value),)
        valid = raw.truth_cutoff_ns
        quality += ("truth-dependent-native-evaluation", "aggregate-cutoff-valid-time")
    elif isinstance(raw, CrossSectionRanking):
        require(raw.spec_id == ref.producer_id, "health frozen ranking spec")
        spec = repo.resolve(CrossSectionSpec, raw.spec_id)
        valid = spec.identity.anchor_origin.timestamp_ns
        values = tuple(
            ("rank:" + e.security.instrument.fingerprint, e.rank) for e in raw.entries
        )
        values += tuple(
            ("score:" + e.security.instrument.fingerprint, e.raw) for e in raw.entries
        )
        quality += ("ranking:" + raw.quality.value,)
    else:
        require(
            identity == ref.artifact_id or identity == ref.producer_id,
            "health exact frozen parameter artifact",
        )
        values = _parameter_values(repo, raw)
    if sample_id is not None:
        sample = repo.resolve(ResearchSample, sample_id)
        require(
            sample.target_definition_id == ref.target_id and sample.origin is not None,
            "health exact sample/target",
        )
        if partition is None and ref.fold_id:
            memberships = [
                m for m in repo.fold_memberships(ref.fold_id) if m.sample_id == sample_id
            ]
            require(len(memberships) == 1, "health exact fold membership")
            partition = memberships[0].partition
    return HealthObservation(
        ref.fingerprint,
        identity,
        valid,
        available,
        values,
        ref.unit,
        quality,
        sample_id,
        security_id,
        partition,
        constructed_ns,
    )


def validate_reference(repo: "HealthRepository", ref: MonitoredArtifactReference) -> None:
    require(
        reference_for(repo, ref.artifact_id, ref.anchor_output_id) == ref,
        "health reference semantic replay",
    )
    repo.get(TargetDefinition, ref.target_id)
