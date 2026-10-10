"""Exact native adapters and independently received external observations."""

from dataclasses import replace
from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibratedForecast
from afre.fusion.artifacts import FusionObservation
from afre.fusion.definitions import FusionSourceReference
from afre.fusion.external import ExternalFusionDefinition, ExternalFusionOutput
from afre.fusion.probabilistic import law_mean
from afre.fusion.schema import FusionKind
from afre.orthogonalization.artifacts import OrthogonalSignalValue, ProjectionArtifact
from afre.orthogonalization.definitions import OrthogonalizationSpec
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.research_datasets.samples import ResearchSample
from afre.schema import require
from afre.uncertainty.sources import source_for

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository

FAMILIES = {
    "PointForecast": "point",
    "ProbabilisticForecast": "probabilistic",
    "CalibratedForecast": "calibrated",
    "EventConditionedForecast": "event",
    "RegimeConditionedForecast": "regime",
    "MixtureForecast": "mixture",
    "NonlinearForecast": "nonlinear",
    "SequenceForecast": "sequence",
}


def reference_for(
    repo: "FusionRepository", output_id: str, kind: FusionKind | None = None
) -> FusionSourceReference:
    raw = repo.get_any(output_id)
    if isinstance(raw, ExternalFusionOutput):
        definition = repo.resolve(ExternalFusionDefinition, raw.definition_id)
        require(kind is None or kind is definition.kind, "external output kind")
        return FusionSourceReference(
            definition.logical_id,
            "external",
            definition.fingerprint,
            definition.version,
            definition.provider,
            definition.target.fingerprint,
            definition.target.horizon.fingerprint,
            definition.kind,
            definition.unit,
            definition.fingerprint,
            definition.fingerprint,
            "external-declared-raw",
            definition.declared_ns,
            output_id,
        )
    if isinstance(raw, OrthogonalSignalValue):
        projection = repo.resolve(ProjectionArtifact, raw.projection_id)
        spec = repo.resolve(OrthogonalizationSpec, projection.spec_id)
        require(kind in (None, FusionKind.SCALAR_SIGNAL), "residual scalar kind")
        return FusionSourceReference(
            projection.fingerprint,
            "orthogonal",
            projection.fingerprint,
            "1.0",
            "AFRE",
            spec.target.fingerprint,
            spec.target.horizon.fingerprint,
            FusionKind.SCALAR_SIGNAL,
            raw.unit,
            projection.fingerprint,
            spec.fingerprint,
            "residual-no-calibration",
            projection.available_ns,
            output_id,
        )
    require(type(raw).__name__ in FAMILIES, "unsupported fusion forecast source")
    source = source_for(repo, output_id)
    model_id = (
        raw.model_artifact_id
        if isinstance(raw, ProbabilisticForecast)
        else raw.state_id
        if isinstance(raw, CalibratedForecast)
        else source.model_id
    )
    model = repo.get_any(model_id)
    spec_id = getattr(
        model,
        "spec_id",
        getattr(
            getattr(model, "inputs", None), "spec_id", getattr(model, "expert_set_id", model_id)
        ),
    )
    available = getattr(
        model,
        "available_ns",
        getattr(
            getattr(model, "inputs", None), "available_ns", getattr(model, "declared_ns", 0)
        ),
    )
    resolved_kind = kind or (
        FusionKind.PROBABILISTIC
        if source.law is not None
        or isinstance(raw, (ProbabilisticForecast, CalibratedForecast))
        else FusionKind.POINT
    )
    require(
        resolved_kind is not FusionKind.SCALAR_SIGNAL, "native forecast is not ordinal signal"
    )
    calibration = "calibrated:" + model_id if isinstance(raw, CalibratedForecast) else "raw"
    return FusionSourceReference(
        model_id,
        FAMILIES[type(raw).__name__],
        model_id,
        "1.0",
        "AFRE",
        source.target.fingerprint,
        source.target.horizon.fingerprint,
        resolved_kind,
        "target-value:" + source.target.fingerprint,
        model_id,
        spec_id,
        calibration,
        available,
        output_id,
    )


def observation_for(
    repo: "FusionRepository",
    reference: FusionSourceReference,
    output_id: str,
    approved_attestors: tuple[str, ...] = (),
) -> FusionObservation:
    require(
        reference
        == replace(
            reference_for(repo, output_id, reference.kind),
            anchor_output_id=reference.anchor_output_id,
        ),
        "exact fusion producer reference",
    )
    raw = repo.get_any(output_id)
    if isinstance(raw, ExternalFusionOutput):
        definition = repo.resolve(ExternalFusionDefinition, raw.definition_id)
        sample = repo.get(ResearchSample, raw.sample_id)
        require(
            sample.origin == raw.origin
            and sample.target_definition_id == reference.target_id
            and not sample.dropped,
            "external exact admitted sample/target/origin",
        )
        proof = raw.clocks.historical_delivery
        require(
            proof is None
            or proof.attestor in approved_attestors
            and proof.source_id == definition.source.fingerprint
            and proof.entity == raw.origin.instrument,
            "approved exact historical delivery",
        )
        require(
            raw.sample_id not in definition.base_train_sample_ids
            and definition.base_fit_cutoff_ns < raw.origin.timestamp_ns,
            "external prediction must be out-of-sample and historically causal",
        )
        return FusionObservation(
            reference.fingerprint,
            output_id,
            raw.sample_id,
            raw.origin,
            law_mean(raw.law)
            if reference.kind is FusionKind.PROBABILISTIC and law_mean(raw.law) is not None
            else raw.value,
            raw.law,
            raw.clocks.final_available_ns,
            approved_attestors,
        )
    if isinstance(raw, OrthogonalSignalValue):
        repo._validate_links(raw)
        return FusionObservation(
            reference.fingerprint,
            output_id,
            raw.sample_id,
            raw.origin,
            raw.residual,
            None,
            raw.available_ns,
            approved_attestors,
        )
    source = source_for(repo, output_id)
    return FusionObservation(
        reference.fingerprint,
        output_id,
        source.sample_id,
        source.origin,
        law_mean(source.law)
        if reference.kind is FusionKind.PROBABILISTIC and law_mean(source.law) is not None
        else source.prediction,
        source.law,
        source.available_ns,
        approved_attestors,
    )
