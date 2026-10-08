"""Bounded hypothetical per-security paths, never a portfolio or execution instruction."""

from typing import TYPE_CHECKING

from afre.costs.artifacts import ResearchExposureChange, ResearchExposurePath
from afre.costs.definitions import CostScenario, ResearchExposureRule
from afre.costs.schema import ResearchExposureMode
from afre.costs.sources import sources_for
from afre.schema import require

if TYPE_CHECKING:
    from afre.costs.repository import CostResearchRepository


def exposure_for(rule: ResearchExposureRule, prediction: float) -> float:
    if rule.mode is ResearchExposureMode.FIXED_UNIT_NOTIONAL:
        return 1.0
    if rule.mode is ResearchExposureMode.DECLARED_SCALAR_EXPOSURE:
        return rule.scalar_exposure
    if abs(prediction) <= rule.threshold:
        return 0.0
    return rule.amplitude if prediction > 0 else -rule.amplitude


def path_for(
    repo: "CostResearchRepository", scenario_id: str, constructed_ns: int
) -> tuple[tuple[ResearchExposureChange, ...], ResearchExposurePath]:
    scenario = repo.resolve(CostScenario, scenario_id)
    sources = sources_for(repo, scenario)
    previous: dict[str, tuple[str, float, int]] = {}
    changes: list[ResearchExposureChange] = []
    for source in sources:
        security = source.origin.instrument.fingerprint
        prev = previous.get(security)
        require(
            prev is None or source.origin.timestamp_ns > prev[2],
            "ambiguous same-time security path/context",
        )
        require(
            constructed_ns >= source.available_ns,
            "actual exposure construction before source forecast",
        )
        prior = scenario.exposure_rule.initial_exposure if prev is None else prev[1]
        exposure = exposure_for(scenario.exposure_rule, source.value)
        changes.append(
            ResearchExposureChange(
                scenario_id,
                source.sample_id,
                source.identity,
                source.origin,
                prev[0] if prev else None,
                prior,
                exposure,
                exposure - prior,
                constructed_ns,
                constructed_ns,
            )
        )
        previous[security] = source.sample_id, exposure, source.origin.timestamp_ns
    result = tuple(sorted(changes, key=lambda c: c.fingerprint))
    return result, ResearchExposurePath(
        scenario_id, tuple(c.fingerprint for c in result), constructed_ns, constructed_ns
    )
