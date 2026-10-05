"""Target-free composition; only exact admitted inputs can influence a forecast."""

from math import fsum
from typing import TYPE_CHECKING

from afre.mixture.artifacts import (
    ExpertContribution,
    GateModelArtifact,
    MixtureComponent,
    MixtureDistribution,
    MixtureForecast,
    MixtureRequest,
)
from afre.mixture.availability import gating_value_for
from afre.mixture.definitions import ExpertSet, FixedGateSpec, LearnedGateSpec
from afre.mixture.experts import ExpertForecastBinding, GatingFeatureReference
from afre.mixture.missingness import binding_reason, effective_weights
from afre.mixture.schema import ExpertOutput, GateMode
from afre.probabilistic.schema import DistributionFamily
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import require
from afre.statistical_models.linear_algebra import finite

if TYPE_CHECKING:
    from afre.mixture.repository import MixtureRepository


def partition_for(repo: "MixtureRepository", fold_id: str, sample: ResearchSample) -> Partition:
    fold = repo.resolve_fold(fold_id)
    dataset = repo.resolve_dataset(fold.dataset_id)
    require(
        sample.fingerprint in dataset.sample_ids
        and not sample.dropped
        and sample.origin is not None,
        "mixture exact eligible dataset sample",
    )
    matches = tuple(
        m for m in repo.fold_memberships(fold_id) if m.sample_id == sample.fingerprint
    )
    require(
        len(matches) == 1
        and matches[0].partition in (Partition.TRAIN, Partition.VALIDATION, Partition.TEST),
        "mixture admitted fold membership",
    )
    return matches[0].partition


def forecast_for(repo: "MixtureRepository", request: MixtureRequest) -> MixtureForecast:
    experts = repo.resolve(ExpertSet, request.expert_set_id)
    require(len(experts.experts) <= repo.mixture_bounds.experts, "mixture expert bound")
    sample = repo.resolve(ResearchSample, request.sample_id)
    partition = partition_for(repo, request.fold_id, sample)
    require(sample.target_definition_id == experts.target.fingerprint, "mixture sample target")
    assert sample.origin is not None
    feature_names: tuple[str, ...]
    if request.gate_id.startswith("afre.mix_fixed_gate:"):
        fixed = repo.resolve(FixedGateSpec, request.gate_id)
        require(
            fixed.expert_set == experts and not request.gating_feature_ids,
            "fixed gate exact expert set; gating features unsupported",
        )
        original, mode, required, feature_names = (
            fixed.weights,
            GateMode.FIXED,
            fixed.available_ns,
            (),
        )
    else:
        gate = repo.resolve(GateModelArtifact, request.gate_id)
        spec = repo.resolve(LearnedGateSpec, gate.spec_id)
        require(
            spec.expert_set == experts
            and request.fold_id == spec.fold_id
            and request.sample_id not in {r.sample_id for r in gate.rows},
            "learned application exact set/fold and non-TRAIN fit sample",
        )
        original, mode, required, feature_names = (
            gate.weights,
            GateMode.LEARNED_LINEAR,
            gate.available_ns,
            spec.gating_feature_ids,
        )
    require(
        tuple(i for i, _ in request.expert_inputs) == experts.expert_ids,
        "mixture request complete expert presence/absence grid",
    )
    require(
        len(request.gating_feature_ids) <= repo.mixture_bounds.gating_features,
        "mixture gating feature bound",
    )
    features = tuple(
        repo.resolve(GatingFeatureReference, i) for i in request.gating_feature_ids
    )
    require(
        tuple(sorted(f.feature_id for f in features)) == feature_names,
        "application exact gating features",
    )
    for f in features:
        gating_value_for(repo, f, experts.approved_delivery_attestors)
        require(f.origin == sample.origin, "mixture gate feature origin")
        required = max(required, f.available_ns)
    bindings = tuple(
        (i, repo.resolve(ExpertForecastBinding, b) if b else None)
        for i, b in request.expert_inputs
    )
    reasons = tuple(
        (i, binding_reason(repo, experts, b, sample) if b else "missing") for i, b in bindings
    )
    effective, fallback = effective_weights(experts, original, reasons)
    contributions = []
    components = []
    probability_state = (
        "point-only" if experts.experts[0].output is ExpertOutput.POINT else "available"
    )
    for (i, b), (_, old), (_, weight), (_, reason) in zip(
        bindings, original, effective, reasons, strict=True
    ):
        usable = reason == "available"
        value = b.point if b and usable else None
        contributions.append(
            ExpertContribution(
                i,
                b.fingerprint if b else None,
                old,
                weight,
                value,
                finite(weight * value) if value is not None else None,
                reason,
            )
        )
        if weight > 0:
            assert b is not None
            required = max(required, b.available_ns)
            if experts.experts[0].output is ExpertOutput.PROBABILISTIC:
                if (
                    b.distribution is None
                    or b.distribution.family is DistributionFamily.QUANTILE_SET
                ):
                    probability_state = "unsupported-sparse-quantile-or-missing-law"
                else:
                    components.append(
                        MixtureComponent(i, b.fingerprint, weight, b.distribution)
                    )
    require(
        required <= sample.origin.availability_cutoff_ns
        and sample.origin.timestamp_ns
        <= request.computed_ns
        <= sample.origin.availability_cutoff_ns,
        "gate/expert/computation unavailable at mixture origin",
    )
    distribution = (
        MixtureDistribution(tuple(components)) if probability_state == "available" else None
    )
    return MixtureForecast(
        request,
        sample.security,
        sample.origin,
        experts.target.fingerprint,
        partition,
        mode,
        tuple(contributions),
        finite(fsum(c.contribution for c in contributions if c.contribution is not None)),
        distribution,
        probability_state,
        fallback,
        max(required, request.computed_ns),
    )
