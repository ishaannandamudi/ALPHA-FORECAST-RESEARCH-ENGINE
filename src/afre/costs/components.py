"""Exact declared rates and liquidity; missing inputs never silently become zero."""

from typing import TYPE_CHECKING

from afre.costs.artifacts import CostComponentEstimate, ResearchExposureChange
from afre.costs.cost_inputs import CostInputReference, input_reason
from afre.costs.definitions import CostComponentSpec, CostScenario
from afre.costs.fees import conversion_factor
from afre.costs.impact import impact_multiplier
from afre.costs.schema import CostInputRole, CostMissingPolicy, CostModel, CostQuality, CostUnit
from afre.costs.spread import observed_full_spread, spread_multiplier
from afre.schema import require

if TYPE_CHECKING:
    from afre.costs.repository import CostResearchRepository


def component_for(
    repo: "CostResearchRepository", change: ResearchExposureChange, component_id: str
) -> CostComponentEstimate:
    scenario = repo.resolve(CostScenario, change.scenario_id)
    spec = repo.resolve(CostComponentSpec, component_id)
    require(spec in scenario.components, "exact declared cost component")
    binding = next(
        b
        for b in scenario.bindings
        if b.sample_id == change.sample_id and b.component_id == component_id
    )
    liquidity = next(a for a in scenario.liquidity if a.sample_id == change.sample_id)
    liquid_ids = tuple(
        i
        for i in (
            liquidity.price_input_id,
            liquidity.notional_input_id,
            liquidity.volume_input_id,
        )
        if i
    )
    liquid = tuple(repo.resolve(CostInputReference, i) for i in liquid_ids)
    expected_roles = (
        CostInputRole.REFERENCE_PRICE,
        CostInputRole.REFERENCE_NOTIONAL,
        *((CostInputRole.AVAILABLE_VOLUME,) if liquidity.volume_input_id else ()),
    )
    require(tuple(i.role for i in liquid) == expected_roles, "exact liquidity role binding")
    liquid_reasons = tuple(
        r
        for i in liquid
        if (r := input_reason(repo, i, scenario, change.origin, change.constructed_ns))
    )
    if len(liquid) < 3 and spec.model in (
        CostModel.LINEAR_PARTICIPATION,
        CostModel.SQRT_PARTICIPATION,
    ):
        liquid_reasons += ("missing-explicit-available-volume",)
    inputs = tuple(repo.resolve(CostInputReference, i) for i in binding.input_ids)
    if spec.model in (CostModel.LINEAR_PARTICIPATION, CostModel.SQRT_PARTICIPATION):
        require(
            all(i.horizon_id == scenario.target.horizon.fingerprint for i in inputs),
            "impact coefficient exact horizon",
        )
    require(
        all(
            i.component is spec.component
            and i.provider == spec.provider
            and i.version == spec.provider_version
            and i.provider_schema == spec.provider_schema
            and i.venue == spec.venue
            and (
                i.role is not CostInputRole.MODEL_VALUE or i.included_components == spec.covers
            )
            for i in inputs
        ),
        "cost applicability provider/version/component/venue",
    )
    input_reasons = tuple(
        r
        for i in inputs
        if (r := input_reason(repo, i, scenario, change.origin, change.constructed_ns))
    )
    rate: float | None = spec.fixed_value
    rate_reason: str | None = None
    if spec.model is CostModel.OBSERVED_BID_ASK_SPREAD:
        require(
            not inputs
            or len(inputs) == 2
            and {i.role for i in inputs} == {CostInputRole.BID, CostInputRole.ASK}
            and all(i.unit is spec.unit for i in inputs),
            "observed spread exact bid/ask shape",
        )
        if inputs and not input_reasons:
            by_role = {i.role: i.value for i in inputs}
            bid, ask = by_role[CostInputRole.BID], by_role[CostInputRole.ASK]
            assert bid is not None and ask is not None
            rate = observed_full_spread(bid, ask)
        else:
            rate_reason = "missing-or-unusable-bid-ask"
    elif spec.fixed_value is None:
        require(
            len(inputs) <= 1
            and all(
                i.role is CostInputRole.MODEL_VALUE and i.unit is spec.unit for i in inputs
            ),
            "exact provider cost coefficient/rate shape",
        )
        rate = inputs[0].value if inputs and not input_reasons else None
        if rate is None:
            rate_reason = "missing-or-unusable-provider-rate"
    else:
        require(not inputs, "fixed cost has no hidden provider input")
    reason = ";".join(
        (*liquid_reasons, *input_reasons, *((rate_reason,) if rate_reason else ()))
    )
    fallback = False
    if (
        not liquid_reasons
        and rate is None
        and scenario.missing_policy is CostMissingPolicy.DECLARED_FALLBACK
    ):
        require(spec.fallback_value is not None, "component fallback not declared")
        rate, fallback = spec.fallback_value, True
    usable = not liquid_reasons and rate is not None
    if not usable:
        require(
            scenario.missing_policy is CostMissingPolicy.EXCLUDE_SAMPLE,
            "missing cost/liquidity requires explicit exclusion or usable declared fallback: "
            + reason,
        )
    factor = participation = quantity = amount = None
    if usable:
        price, notional = liquid[0].value, liquid[1].value
        assert price is not None and notional is not None and rate is not None
        quantity = abs(change.trade_delta) * notional / price
        if len(liquid) == 3:
            volume = liquid[2].value
            assert volume is not None
            participation = quantity / volume
            require(
                participation <= scenario.maximum_participation,
                "hypothetical participation exceeds declared bound",
            )
        if spec.model in (CostModel.LINEAR_PARTICIPATION, CostModel.SQRT_PARTICIPATION):
            require(participation is not None, "impact requires explicit available volume")
        factor = conversion_factor(
            spec.unit, spec.basis, change.trade_delta, price, notional
        ) * spread_multiplier(spec.spread_meaning)
        amount = rate * factor * impact_multiplier(spec.model, participation)
    quality = (
        CostQuality.MISSING
        if amount is None
        else CostQuality.DEGRADED
        if fallback or any(i.quality is CostQuality.DEGRADED for i in (*inputs, *liquid))
        else CostQuality.VALID
    )
    return CostComponentEstimate(
        scenario.fingerprint,
        change.fingerprint,
        component_id,
        binding.input_ids,
        liquid_ids,
        rate,
        spec.unit,
        factor,
        participation,
        quantity,
        amount,
        CostUnit.RETURN_FRACTION,
        quality,
        reason or "explicit-cost-inputs-and-unit-conversion",
        fallback,
        scenario.timing,
        change.constructed_ns,
        change.available_ns,
    )
