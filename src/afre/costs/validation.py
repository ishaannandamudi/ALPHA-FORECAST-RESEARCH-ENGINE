"""Replay cost results from exact immutable sources and predeclared settings."""

from typing import TYPE_CHECKING

from afre.costs.artifacts import (
    BreakEvenCostDiagnostic,
    CostAwareComparison,
    CostAwareEvaluation,
    CostAwareSampleEvaluation,
    CostCohortEvaluation,
    CostComponentEstimate,
    CostResearchAudit,
    CostSensitivityCurve,
    ResearchExposureChange,
    ResearchExposurePath,
    TotalCostEstimate,
)
from afre.costs.cost_inputs import CostInputReference
from afre.costs.definitions import (
    CostComponentSpec,
    CostScenario,
    CostSensitivitySpec,
    ResearchExposureRule,
)
from afre.costs.schema import CostInputRole, CostModel
from afre.costs.sources import sources_for
from afre.feature_store.models import SourceReference
from afre.research_datasets.splits import TestEvaluation
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.costs.repository import CostResearchRepository


def validate_costs(repo: "CostResearchRepository", value: Artifact) -> None:
    from afre.costs.breakeven import breakeven_for
    from afre.costs.cohorts import cohort_for
    from afre.costs.comparisons import comparison_for
    from afre.costs.components import component_for
    from afre.costs.evaluation import evaluation_for, sample_for
    from afre.costs.exposures import path_for
    from afre.costs.lineage import audit_for
    from afre.costs.sensitivity import sensitivity_for, validate_sensitivity
    from afre.costs.totals import total_for

    expected = value
    if isinstance(value, CostInputReference):
        require(
            repo.resolve(SourceReference, value.source.fingerprint) == value.source,
            "exact cost provenance source",
        )
        if value.clocks.historical_delivery:
            require(
                repo.get_any(value.clocks.historical_delivery.fingerprint)
                == value.clocks.historical_delivery,
                "exact qualified cost delivery contract",
            )
    elif isinstance(value, CostScenario):
        sources = {s.sample_id: s for s in sources_for(repo, value)}
        require(
            repo.resolve(ResearchExposureRule, value.exposure_rule.fingerprint)
            == value.exposure_rule
            and all(
                repo.resolve(CostComponentSpec, c.fingerprint) == c for c in value.components
            ),
            "exact declared rule and component settings",
        )
        for b in value.bindings:
            component = next(c for c in value.components if c.fingerprint == b.component_id)
            inputs = tuple(repo.resolve(CostInputReference, i) for i in b.input_ids)
            require(
                all(
                    i.security == sources[b.sample_id].origin.instrument
                    and i.currency == value.currency
                    and (
                        i.horizon_id is None or i.horizon_id == value.target.horizon.fingerprint
                    )
                    and i.component is component.component
                    and i.provider == component.provider
                    and i.version == component.provider_version
                    and i.provider_schema == component.provider_schema
                    and i.venue == component.venue
                    and (
                        i.role is not CostInputRole.MODEL_VALUE
                        or i.included_components == component.covers
                    )
                    and i.unit is component.unit
                    for i in inputs
                ),
                "scenario exact input security/currency/horizon/provider/units",
            )
            if component.fixed_value is not None:
                require(not inputs, "fixed scenario rate has no hidden provider input")
            elif component.model is CostModel.OBSERVED_BID_ASK_SPREAD:
                require(
                    not inputs
                    or len(inputs) == 2
                    and {i.role for i in inputs} == {CostInputRole.BID, CostInputRole.ASK},
                    "scenario exact bid/ask input shape",
                )
            else:
                require(
                    len(inputs) <= 1
                    and all(i.role is CostInputRole.MODEL_VALUE for i in inputs),
                    "scenario exact provider coefficient shape",
                )
            for identity in b.input_ids:
                repo.resolve(CostInputReference, identity)
        for a in value.liquidity:
            liquid = tuple(
                repo.resolve(CostInputReference, i)
                for i in (a.price_input_id, a.notional_input_id, a.volume_input_id)
                if i
            )
            require(
                tuple(i.role for i in liquid)
                == (
                    CostInputRole.REFERENCE_PRICE,
                    CostInputRole.REFERENCE_NOTIONAL,
                    *((CostInputRole.AVAILABLE_VOLUME,) if a.volume_input_id else ()),
                )
                and all(
                    i.security == sources[a.sample_id].origin.instrument
                    and i.currency == value.currency
                    and (
                        i.horizon_id is None or i.horizon_id == value.target.horizon.fingerprint
                    )
                    for i in liquid
                ),
                "scenario exact liquidity applicability",
            )
            for liquid_id in (a.price_input_id, a.notional_input_id, a.volume_input_id):
                if liquid_id:
                    repo.resolve(CostInputReference, liquid_id)
    elif isinstance(value, CostSensitivitySpec):
        validate_sensitivity(repo, value)
    elif isinstance(value, ResearchExposureChange):
        changes, _ = path_for(repo, value.scenario_id, value.constructed_ns)
        expected = next(c for c in changes if c.sample_id == value.sample_id)
    elif isinstance(value, ResearchExposurePath):
        changes, expected = path_for(repo, value.scenario_id, value.constructed_ns)
        require(
            all(repo.resolve(ResearchExposureChange, c.fingerprint) == c for c in changes),
            "exact persisted exposure path changes",
        )
    elif isinstance(value, CostComponentEstimate):
        expected = component_for(
            repo, repo.resolve(ResearchExposureChange, value.change_id), value.component_id
        )
    elif isinstance(value, TotalCostEstimate):
        expected = total_for(repo, value.change_id, value.component_ids)
    elif isinstance(value, CostAwareSampleEvaluation):
        expected = sample_for(
            repo, value.total_cost_id, value.evaluation_cutoff_ns, value.available_ns
        )
    elif isinstance(value, CostAwareEvaluation):
        seal = (
            repo.resolve(TestEvaluation, value.test_evaluation_id)
            if value.test_evaluation_id
            else None
        )
        expected = evaluation_for(
            repo,
            value.path_id,
            value.sample_evaluation_ids,
            value.evaluation_cutoff_ns,
            value.available_ns,
            seal,
        )
    elif isinstance(value, BreakEvenCostDiagnostic):
        expected = breakeven_for(
            repo, value.evaluation_id, value.component_id, value.available_ns
        )
    elif isinstance(value, CostSensitivityCurve):
        expected = sensitivity_for(repo, value.evaluation_id, value.spec_id, value.available_ns)
    elif isinstance(value, CostAwareComparison):
        expected = comparison_for(repo, value.left_id, value.right_id, value.available_ns)
    elif isinstance(value, CostCohortEvaluation):
        expected = cohort_for(
            repo,
            value.evaluation_id,
            value.environment_id,
            value.membership_ids,
            value.available_ns,
        )
    elif isinstance(value, CostResearchAudit):
        expected = audit_for(repo, value.root_id)
    require(value == expected, "cost research semantic replay mismatch/forged result")
