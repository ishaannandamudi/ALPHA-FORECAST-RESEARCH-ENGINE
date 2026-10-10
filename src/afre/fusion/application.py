"""Target-free immutable application and exact per-sample contribution witnesses."""

from math import fsum
from typing import TYPE_CHECKING

from afre.fusion.artifacts import (
    FusedForecast,
    FusionArtifact,
    FusionContribution,
    FusionObservation,
)
from afre.fusion.compatibility import observations
from afre.fusion.definitions import FusionSpec
from afre.fusion.missingness import effective_weights
from afre.fusion.probabilistic import blend, mean
from afre.fusion.schema import FusionKind, FusionMissingness, FusionStatus
from afre.research_datasets.samples import ResearchSample
from afre.schema import require
from afre.statistical_models.linear_algebra import finite

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository


def forecast_for(
    repo: "FusionRepository",
    artifact_id: str,
    sample_id: str,
    ids: tuple[str, ...],
    computed_ns: int,
    fallback_id: str | None = None,
) -> FusedForecast:
    require(repo._feature_only_depth > 0, "mandatory target-free fusion application guard")
    artifact = repo.resolve(FusionArtifact, artifact_id)
    spec = repo.resolve(FusionSpec, artifact.spec_id)
    sample = repo.get(ResearchSample, sample_id)
    obs = observations(repo, spec, sample_id, ids)
    assert sample.origin is not None
    parts = {
        m.partition for m in repo.fold_memberships(spec.fold_id) if m.sample_id == sample_id
    }
    require(len(parts) == 1, "fusion exact admitted fold partition")
    partition = next(iter(parts))
    weights = dict(effective_weights(spec, artifact, obs))
    by_source = {o.source_id: o for o in obs}
    law = None
    contributions = []
    for j, (i, w) in enumerate(artifact.weights):
        o = by_source.get(i)
        number = (
            finite((o.value - artifact.centers[j]) / artifact.scales[j])
            if o is not None and o.value is not None and i in weights
            else None
        )
        weight = weights.get(i, 0.0)
        contributions.append(
            FusionContribution(
                i,
                o.fingerprint if o else None,
                o.output_id if o else None,
                w,
                weight,
                number,
                finite(number * weight) if number is not None else None,
                "used" if number is not None else "missing-policy",
            )
        )
    used = tuple(o for o in obs if o.source_id in weights)
    value = (
        finite(
            fsum(c.weighted_value for c in contributions if c.weighted_value is not None)
            + artifact.intercept
        )
        if weights
        else None
    )
    reason = "frozen-weighted-sum" if weights else "missing-source-unavailable"
    if spec.kind is FusionKind.PROBABILISTIC and weights:
        require(
            all(o.law is not None for o in used),
            "INCOMPATIBLE: quantile-only/marginal source has no full law",
        )
        law = blend(
            tuple(
                (o.source_id, o.output_id, weights[o.source_id], o.law)
                for o in used
                if o.law is not None
            ),
            min(spec.bounds.probability_components, repo.fusion_bounds.probability_components),
        )
        require(
            sum(len(c.distribution.samples) or 1 for c in law.components)
            <= min(spec.bounds.probability_atoms, repo.fusion_bounds.probability_atoms),
            "fusion probability atom bound",
        )
        value = mean(law)
    if not weights and spec.missingness is FusionMissingness.USE_DECLARED_FALLBACK:
        require(fallback_id is not None, "declared fallback observation required")
        assert fallback_id is not None
        fallback = repo.resolve(FusionObservation, fallback_id)
        require(
            fallback.source_id == spec.fallback_source_id
            and fallback.sample_id == sample_id
            and fallback.origin == sample.origin,
            "exact declared fallback sample/source",
        )
        value = fallback.value
        used = (fallback,)
        contributions = [
            FusionContribution(
                fallback.source_id,
                fallback.fingerprint,
                fallback.output_id,
                1.0,
                1.0,
                value,
                value,
                "declared-fallback",
            )
        ]
        if spec.kind is FusionKind.PROBABILISTIC and value is not None:
            require(fallback.law is not None, "fallback full probability law required")
            assert fallback.law is not None
            law = blend(
                ((fallback.source_id, fallback.output_id, 1.0, fallback.law),),
                min(
                    spec.bounds.probability_components,
                    repo.fusion_bounds.probability_components,
                ),
            )
            value = mean(law)
        reason = "declared-fallback"
    else:
        require(fallback_id is None, "unused/undeclared fallback observation")
    if law is not None:
        require(
            sum(len(c.distribution.samples) or 1 for c in law.components)
            <= min(spec.bounds.probability_atoms, repo.fusion_bounds.probability_atoms),
            "fusion probability atom bound",
        )
    available = max(computed_ns, artifact.available_ns, *(o.available_ns for o in used))
    require(
        artifact.available_ns <= sample.origin.availability_cutoff_ns,
        "fusion fit artifact unavailable at use origin",
    )
    return FusedForecast(
        artifact_id,
        sample_id,
        sample.security,
        sample.origin,
        spec.target_id,
        spec.horizon_id,
        spec.output_unit or spec.unit,
        spec.fold_id,
        partition,
        ids,
        fallback_id,
        tuple(contributions),
        0.0 if reason == "declared-fallback" else artifact.intercept,
        FusionStatus.AVAILABLE if value is not None else FusionStatus.UNAVAILABLE,
        reason,
        value,
        law,
        computed_ns,
        available,
    )
