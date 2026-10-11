"""Private native adapters. Public consumers only receive service contracts."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibratedForecast, CalibrationState
from afre.calibration.definitions import CalibrationSpec
from afre.forecast import ForecastOrigin
from afre.fusion.artifacts import FusedForecast
from afre.fusion.probabilistic import FusionDistribution
from afre.mixture.artifacts import MixtureDistribution
from afre.probabilistic.artifacts import DistributionParameters, ProbabilisticForecast
from afre.probabilistic.schema import DistributionFamily
from afre.research_datasets.samples import ResearchSample
from afre.schema import Artifact, require
from afre.service.outputs import (
    ForecastOutput,
    ServiceCalibration,
    ServiceLawComponent,
    ServiceProbabilityLaw,
)
from afre.target_engine.definitions import TargetDefinition
from afre.uncertainty.sources import source_for
from afre.universe.identity import StableSecurityId

if TYPE_CHECKING:
    from afre.service.repository import ServiceRepository


@dataclass(frozen=True)
class NativeSnapshotSource:
    artifact: Artifact
    security: StableSecurityId
    origin: ForecastOrigin
    target: TargetDefinition
    sample: ResearchSample
    producer_id: str
    output: ForecastOutput


def law_component(
    identity: str, weight: float, law: DistributionParameters
) -> ServiceLawComponent:
    family = {
        DistributionFamily.GAUSSIAN_LOCATION_SCALE: "GAUSSIAN",
        DistributionFamily.EMPIRICAL_RESIDUAL: "EMPIRICAL",
        DistributionFamily.QUANTILE_SET: "QUANTILES",
    }[law.family]
    return ServiceLawComponent(
        identity,
        weight,
        family,
        law.location,
        law.scale if family == "GAUSSIAN" else 0.0,
        tuple(law.location + a for a in law.samples),
        tuple((q.level, q.value) for q in law.quantile_values),
    )


def public_law(
    law: DistributionParameters | MixtureDistribution | FusionDistribution | None,
) -> ServiceProbabilityLaw | None:
    if law is None:
        return None
    if isinstance(law, DistributionParameters):
        component = law_component(law.fingerprint, 1.0, law)
        return ServiceProbabilityLaw(component.family, law.fingerprint, (component,))
    return ServiceProbabilityLaw(
        "MIXTURE",
        law.fingerprint,
        tuple(
            law_component(
                getattr(c, "component_id", getattr(c, "expert_id", "native-component")),
                c.weight,
                c.distribution,
            )
            for c in law.components
        ),
    )


def native_source(repo: "ServiceRepository", identity: str) -> NativeSnapshotSource:
    if repo._service_request_depth and identity in repo._service_sources:
        return repo._service_sources[identity]
    result = _native_source(repo, identity)
    if repo._service_request_depth:
        repo._service_sources[identity] = result
    return result


def _native_source(repo: "ServiceRepository", identity: str) -> NativeSnapshotSource:
    law: DistributionParameters | MixtureDistribution | FusionDistribution | None
    raw = repo.get_any(identity)
    if isinstance(raw, FusedForecast):
        repo._validate_links(raw)
        require(raw.value is not None, "INSUFFICIENT_DATA: fusion output unavailable")
        sample = repo.resolve(ResearchSample, raw.sample_id)
        target = repo.resolve(TargetDefinition, raw.target_id)
        origin, producer, point, law, unit = (
            raw.origin,
            raw.artifact_id,
            raw.value,
            raw.law,
            raw.unit,
        )
    else:
        source = source_for(repo, identity)
        sample = repo.resolve(ResearchSample, source.sample_id)
        target, origin, point, law = source.target, source.origin, source.prediction, source.law
        producer = (
            raw.model_artifact_id
            if isinstance(raw, ProbabilisticForecast)
            else raw.state_id
            if isinstance(raw, CalibratedForecast)
            else source.model_id
        )
        unit = "target-value:" + target.fingerprint
    require(
        sample.origin == origin
        and sample.target_definition_id == target.fingerprint
        and not sample.dropped,
        "INCOMPATIBLE: exact admitted sample/target/origin",
    )
    available = getattr(raw, "available_ns", None)
    require(type(available) is int, "INCOMPATIBLE: source availability")
    assert isinstance(available, int)
    require(
        available <= origin.availability_cutoff_ns
        and getattr(raw, "historical_admissible", True),
        "INCOMPATIBLE: late source",
    )
    calibration = ServiceCalibration("UNCALIBRATED", "NONE", None, "1.0", None, None, False)
    interval = None
    if isinstance(raw, CalibratedForecast):
        state = repo.get(CalibrationState, raw.state_id)
        spec = repo.get(CalibrationSpec, state.inputs.spec_id)
        calibration = ServiceCalibration(
            "CALIBRATED",
            spec.method.value,
            raw.state_id,
            "1.0",
            state.inputs.cutoff_ns,
            raw.calibration_available_ns,
            raw.full_distribution_preserved,
        )
        if raw.calibrated_interval:
            interval = (raw.calibrated_interval.lower, raw.calibrated_interval.upper)
    quantiles = tuple((q.level, q.value) for q in getattr(raw, "quantiles", ()))
    probabilities = tuple(
        (p.request.comparison.name, p.request.value, p.probability)
        for p in getattr(raw, "probabilities", getattr(raw, "threshold_probabilities", ()))
    )
    output = ForecastOutput(
        identity,
        producer,
        target.fingerprint,
        target.horizon.fingerprint,
        unit,
        point,
        public_law(law),
        quantiles,
        probabilities,
        interval,
        calibration,
        available,
    )
    return NativeSnapshotSource(raw, sample.security, origin, target, sample, producer, output)
