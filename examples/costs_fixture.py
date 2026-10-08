"""Neutral offline native forecasts and explicit provider-bound hypothetical costs."""

from dataclasses import dataclass, replace

from afre.costs import (
    CostBasis,
    CostComponentSpec,
    CostComponentType,
    CostInputBinding,
    CostInputReference,
    CostInputRole,
    CostMissingPolicy,
    CostModel,
    CostQuality,
    CostResearchEngine,
    CostResearchRepository,
    CostScenario,
    CostTiming,
    CostUnit,
    InitialExposurePolicy,
    ResearchExposureMode,
    ResearchExposureRule,
    ResearchLiquidityAssumption,
    SpreadMeaning,
)
from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.hashing import bytes_digest
from afre.invariance import StabilityAnalysisSpec
from afre.lineage import ProvenanceRef
from afre.research_datasets.samples import ResearchSample
from examples.invariance_fixture import InvarianceFixture
from examples.invariance_fixture import build_fixture as invariance_fixture


@dataclass(frozen=True)
class CostFixture:
    upstream: InvarianceFixture
    scenario: CostScenario
    inputs: tuple[CostInputReference, ...]


def neutral_input(
    sample: ResearchSample,
    component: CostComponentType,
    role: CostInputRole,
    value: float | None,
    unit: CostUnit,
    quality: CostQuality = CostQuality.VALID,
    late_ns: int = 0,
    revision: str = "1",
    horizon_id: str | None = None,
) -> CostInputReference:
    at = sample.timestamp_ns
    assert sample.origin is not None
    provider = "neutral-cost-provider"
    source = SourceReference(
        ProvenanceRef(
            provider,
            f"{sample.fingerprint}:{component.value}:{role.value}:{revision}",
            "1",
            bytes_digest(str(value).encode()),
        ),
        ProvenanceRef(
            provider, "neutral-cost-dataset", "1", bytes_digest(b"costs")
        ).fingerprint,
    )
    return CostInputReference(
        component,
        role,
        provider,
        "1",
        "1.0",
        source,
        sample.origin.instrument,
        unit,
        "USD",
        at,
        AvailabilityEvidence(
            at + late_ns,
            at + late_ns,
            at + late_ns,
            at + late_ns,
            upstream_publication_ns=at,
            upstream_available_ns=at,
        ),
        quality,
        value,
        revision=revision,
        horizon_id=horizon_id,
        included_components=(component,) if role is CostInputRole.MODEL_VALUE else (),
    )


def component(
    name: str,
    kind: CostComponentType,
    model: CostModel,
    unit: CostUnit,
    fixed: float | None = None,
    *,
    basis: CostBasis = CostBasis.PER_SIDE_PER_TURNOVER,
    meaning: SpreadMeaning = SpreadMeaning.NOT_SPREAD,
) -> CostComponentSpec:
    return CostComponentSpec(
        name,
        kind,
        model,
        "1",
        unit,
        basis,
        meaning,
        (kind,),
        40,
        fixed_value=fixed,
        provider="neutral-cost-provider",
        provider_version="1",
        provider_schema="1.0",
    )


def declare_scenario(
    repo: CostResearchRepository,
    spec: StabilityAnalysisSpec,
    reverse: bool = False,
    *,
    publish: bool = True,
) -> tuple[CostScenario, tuple[CostInputReference, ...]]:
    engine = CostResearchEngine(repo)
    definitions: tuple[CostComponentSpec, ...] = (
        component(
            "observed-spread",
            CostComponentType.SPREAD,
            CostModel.OBSERVED_BID_ASK_SPREAD,
            CostUnit.PRICE,
            meaning=SpreadMeaning.FULL_SPREAD,
        ),
        component(
            "fee",
            CostComponentType.EXPLICIT_FEE,
            CostModel.FIXED_RATE,
            CostUnit.CURRENCY_PER_UNIT,
            0.01,
        ),
        component(
            "slippage",
            CostComponentType.SLIPPAGE,
            CostModel.FIXED_RATE,
            CostUnit.BASIS_POINTS,
            1.0,
        ),
        component(
            "impact",
            CostComponentType.MARKET_IMPACT,
            CostModel.LINEAR_PARTICIPATION,
            CostUnit.BASIS_POINTS,
        ),
        component(
            "neutral-tca",
            CostComponentType.CUSTOM_COST,
            CostModel.PROVIDER_ESTIMATE,
            CostUnit.BASIS_POINTS,
        ),
    )
    definitions = tuple(replace(d, declared_ns=spec.declared_ns) for d in definitions)
    inputs: list[CostInputReference] = []
    bindings = []
    liquidities = []
    for sample_id in reversed(spec.sample_ids) if reverse else spec.sample_ids:
        sample = repo.get(ResearchSample, sample_id)
        liquid = tuple(
            neutral_input(
                sample,
                CostComponentType.CUSTOM_COST,
                role,
                value,
                unit,
                horizon_id=spec.target.horizon.fingerprint
                if role is CostInputRole.AVAILABLE_VOLUME
                else None,
            )
            for role, value, unit in (
                (CostInputRole.REFERENCE_PRICE, 100.0, CostUnit.PRICE),
                (CostInputRole.REFERENCE_NOTIONAL, 10_000.0, CostUnit.CURRENCY_TOTAL),
                (CostInputRole.AVAILABLE_VOLUME, 10_000.0, CostUnit.UNIT_QUANTITY),
            )
        )
        liquidities.append(
            ResearchLiquidityAssumption(
                sample_id, liquid[0].fingerprint, liquid[1].fingerprint, liquid[2].fingerprint
            )
        )
        inputs.extend(liquid)
        for d in reversed(definitions) if reverse else definitions:
            values: tuple[CostInputReference, ...] = ()
            if d.model is CostModel.OBSERVED_BID_ASK_SPREAD:
                values = tuple(
                    neutral_input(sample, d.component, role, value, CostUnit.PRICE)
                    for role, value in ((CostInputRole.BID, 99.98), (CostInputRole.ASK, 100.02))
                )
            elif d.fixed_value is None:
                values = (
                    neutral_input(
                        sample,
                        d.component,
                        CostInputRole.MODEL_VALUE,
                        20.0 if d.component is CostComponentType.MARKET_IMPACT else 0.5,
                        CostUnit.BASIS_POINTS,
                        horizon_id=spec.target.horizon.fingerprint
                        if d.component is CostComponentType.MARKET_IMPACT
                        else None,
                    ),
                )
            inputs.extend(values)
            bindings.append(
                CostInputBinding(
                    sample_id,
                    d.fingerprint,
                    tuple(v.fingerprint for v in reversed(values))
                    if reverse
                    else tuple(v.fingerprint for v in values),
                )
            )
    for value in reversed(inputs) if reverse else inputs:
        engine.publish_input(value)
    rule = ResearchExposureRule(
        ResearchExposureMode.SIGN,
        -1.0,
        1.0,
        1.0,
        0.0,
        0.0,
        InitialExposurePolicy.ZERO,
        0.0,
        spec.declared_ns,
    )
    scenario = CostScenario(
        scenario_id="neutral-historical",
        target=spec.target,
        fold_id=spec.fold_id,
        source_ids=spec.forecast_ids,
        sample_ids=spec.sample_ids,
        exposure_rule=rule,
        components=definitions,
        bindings=tuple(bindings),
        liquidity=tuple(liquidities),
        timing=CostTiming.HISTORICAL_CAUSAL,
        missing_policy=CostMissingPolicy.FAIL,
        currency="USD",
        signal_unit="return_fraction",
        maximum_participation=0.1,
        maximum_input_age_ns=0,
        declared_ns=spec.declared_ns,
    )
    if publish:
        engine.declare(scenario)
    return scenario, tuple(inputs)


def declare_fixture(
    repo: CostResearchRepository,
    upstream: InvarianceFixture,
    reverse: bool = False,
    *,
    publish: bool = True,
) -> CostFixture:
    scenario, inputs = declare_scenario(repo, upstream.spec, reverse, publish=publish)
    return CostFixture(upstream, scenario, inputs)


def build_fixture(repo: CostResearchRepository, reverse: bool = False) -> CostFixture:
    return declare_fixture(repo, invariance_fixture(repo, reverse), reverse)
