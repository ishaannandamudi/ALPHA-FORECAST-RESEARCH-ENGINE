"""Explicit whole-request failure, declared drop normalization or exact fallback."""

from math import fsum
from typing import TYPE_CHECKING

from afre.mixture.definitions import ExpertSet
from afre.mixture.experts import ExpertForecastBinding, ExternalExpertForecast
from afre.mixture.schema import ExpertMissingPolicy, ExpertQuality
from afre.research_datasets.samples import ResearchSample
from afre.schema import require

if TYPE_CHECKING:
    from afre.mixture.repository import MixtureRepository


def binding_reason(
    repo: "MixtureRepository",
    experts: ExpertSet,
    binding: ExpertForecastBinding,
    sample: ResearchSample,
) -> str:
    require(
        binding.expert_id in experts.expert_ids
        and binding.target_definition_id == experts.target.fingerprint
        and binding.origin == sample.origin
        and (binding.sample_id is None or binding.sample_id == sample.fingerprint),
        "mixture binding exact expert/target/full-origin/sample mismatch",
    )
    expert = experts.experts[experts.expert_ids.index(binding.expert_id)]
    if expert.quality is not ExpertQuality.VALID:
        return "producer:" + str(expert.quality.value)
    if binding.quality is not ExpertQuality.VALID:
        return "forecast:" + str(binding.quality.value)
    value = repo.get_any(binding.forecast_id)
    if (
        isinstance(value, ExternalExpertForecast)
        and value.clocks.historical_delivery
        and value.clocks.historical_delivery.attestor not in experts.approved_delivery_attestors
    ):
        return "unqualified-historical-delivery"
    assert sample.origin is not None
    if binding.available_ns > sample.origin.availability_cutoff_ns:
        return "not-available-by-origin"
    if sample.timestamp_ns - binding.as_of_ns > experts.maximum_age_ns:
        return "stale"
    if binding.point is None:
        return "unsupported-point-expectation"
    return "available"


def effective_weights(
    experts: ExpertSet,
    original: tuple[tuple[str, float], ...],
    reasons: tuple[tuple[str, str], ...],
) -> tuple[tuple[tuple[str, float], ...], str | None]:
    states = dict(reasons)
    require(tuple(states) == experts.expert_ids, "exact expert absence grid")
    missing = any(w > 0 and states[i] != "available" for i, w in original)
    if not missing:
        return original, None
    require(
        experts.missing_policy is not ExpertMissingPolicy.FAIL, "missing expert FAIL policy"
    )
    if experts.missing_policy is ExpertMissingPolicy.USE_DECLARED_FALLBACK:
        fallback = experts.fallback_id
        require(
            fallback is not None and states[fallback] == "available",
            "declared fallback expert unavailable",
        )
        return tuple((i, 1.0 if i == fallback else 0.0) for i, _ in original), fallback
    total = fsum(w for i, w in original if states[i] == "available")
    require(total > 0, "drop policy has no positive available mass")
    return tuple((i, w / total if states[i] == "available" else 0.0) for i, w in original), None
