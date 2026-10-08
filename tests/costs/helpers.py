"""Exact explicit scenario variants, preserving native sample/source identities."""

from dataclasses import replace

from afre.costs import CostComponentSpec, CostInputReference, CostScenario
from tests.costs.conftest import CostCase


def with_components(
    scenario: CostScenario, components: tuple[CostComponentSpec, ...], tag: str
) -> CostScenario:
    names = {c.fingerprint: c.name for c in scenario.components}
    ids = {c.name: c.fingerprint for c in components}
    bindings = tuple(
        replace(b, component_id=ids[names[b.component_id]])
        for b in scenario.bindings
        if names[b.component_id] in ids
    )
    return replace(scenario, scenario_id=tag, components=components, bindings=bindings)


def replace_input(
    case: CostCase, scenario: CostScenario, old_id: str, value: CostInputReference, tag: str
) -> CostScenario:
    case.engine.publish_input(value)
    bindings = tuple(
        replace(
            b, input_ids=tuple(value.fingerprint if i == old_id else i for i in b.input_ids)
        )
        for b in scenario.bindings
    )
    liquidity = tuple(
        replace(
            a,
            price_input_id=value.fingerprint
            if a.price_input_id == old_id
            else a.price_input_id,
            notional_input_id=value.fingerprint
            if a.notional_input_id == old_id
            else a.notional_input_id,
            volume_input_id=value.fingerprint
            if a.volume_input_id == old_id
            else a.volume_input_id,
        )
        for a in scenario.liquidity
    )
    return replace(scenario, scenario_id=tag, bindings=bindings, liquidity=liquidity)
