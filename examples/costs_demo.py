"""Forty checked offline stages of explicit hypothetical cost research, no execution."""

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.costs import (
    CostComponentSpec,
    CostComponentType,
    CostInputRole,
    CostModel,
    CostResearchEngine,
    CostResearchRepository,
    CostSensitivitySpec,
    CostTiming,
    CostUnit,
    SpreadMeaning,
)
from afre.costs.artifacts import (
    CostAwareSampleEvaluation,
    CostComponentEstimate,
    ResearchExposureChange,
    TotalCostEstimate,
)
from afre.costs.schema import CostResultState
from afre.invariance import EnvironmentMembership, StabilityAnalysisSpec
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import ContractError, require
from afre.serialization import canonical_json
from afre.target_engine.market_data import TargetBar
from afre.target_engine.models import TargetVintage
from examples.costs_fixture import declare_fixture, declare_scenario, neutral_input
from examples.costs_workflow import (
    assess,
    component_variant,
    corrected_input,
    point_scenario,
    subset_source,
)
from examples.invariance_cohorts import build_cohorts
from examples.invariance_fixture import build_fixture, native_forecasts
from examples.invariance_horizons import horizon_analyses

STEPS = (
    "create causal forecast/signal",
    "define explicit exposure mapping",
    "define initial exposure policy",
    "define fixed spread cost",
    "define neutral observed spread input",
    "define explicit fee",
    "define fixed slippage",
    "define linear impact model",
    "define neutral external impact estimate",
    "define HISTORICAL_CAUSAL scenario",
    "define EX_POST_RESEARCH scenario",
    "construct exposure path",
    "calculate trade deltas",
    "calculate turnover",
    "calculate gross contributions",
    "calculate spread costs",
    "calculate fees",
    "calculate slippage",
    "calculate impact",
    "calculate total costs",
    "calculate net contributions",
    "aggregate gross/net diagnostics",
    "calculate break-even total cost",
    "calculate break-even spread/slippage",
    "run supplied cost sensitivity grid",
    "run supplied participation sensitivity grid",
    "compare two supplied signals on exact matched samples",
    "event cohort breakdown",
    "regime breakdown",
    "PIT sector/universe breakdown",
    "AFRE-17 environment breakdown",
    "actual 1h/1d evaluations",
    "prove TEST perturbation cannot alter scenario",
    "prove target-free pre-evaluation metadata",
    "insert corrected cost evidence",
    "prove old evaluation unchanged",
    "rebuild new identity",
    "persist/restart",
    "deterministic replay",
    "bounded audit/lineage",
)


def run(path: Path, reverse: bool = False) -> dict[str, object]:
    evidence: list[object] = [None] * 40
    with CostResearchRepository(path) as repo:
        upstream = build_fixture(repo, reverse)
        f = declare_fixture(repo, upstream, reverse, publish=False)
        engine = CostResearchEngine(repo)
        s = f.scenario
        spread = next(c for c in s.components if c.component is CostComponentType.SPREAD)
        impact = next(c for c in s.components if c.component is CostComponentType.MARKET_IMPACT)
        fixed = replace(
            spread,
            model=CostModel.FIXED_HALF_SPREAD,
            unit=CostUnit.BASIS_POINTS,
            spread_meaning=SpreadMeaning.HALF_SPREAD,
            fixed_value=2.0,
        )
        fixed_s = component_variant(s, fixed, "fixed-half-spread", fixed=True)
        provider_s = component_variant(
            s, replace(impact, model=CostModel.PROVIDER_ESTIMATE), "neutral-impact-estimate"
        )
        ex_post = replace(s, scenario_id="declared-ex-post", timing=CostTiming.EX_POST_RESEARCH)
        point = point_scenario(repo, f)
        scenarios = (s, fixed_s, provider_s, ex_post, point)
        for scenario in reversed(scenarios) if reverse else scenarios:
            engine.declare(scenario)
        impact_grid = CostSensitivitySpec(
            s.fingerprint, impact.fingerprint, (0.0, 10.0, 20.0), (0.0, 0.01, 0.1), (1.0,), 40
        )
        slip = next(c for c in s.components if c.component is CostComponentType.SLIPPAGE)
        cost_grid = CostSensitivitySpec(
            s.fingerprint, slip.fingerprint, (0.0, 1.0, 2.0, 5.0, 10.0), (), (1.0, 2.0), 40
        )
        for grid in (cost_grid, impact_grid) if reverse else (impact_grid, cost_grid):
            engine.register_sensitivity(grid)
        results = {
            v.fingerprint: assess(engine, v)[2]
            for v in (reversed(scenarios) if reverse else scenarios)
        }
        result = results[s.fingerprint]
        path_value = repo.get_any(result.path_id)
        rows = tuple(
            repo.resolve(CostAwareSampleEvaluation, i) for i in result.sample_evaluation_ids
        )
        changes = tuple(repo.resolve(ResearchExposureChange, r.change_id) for r in rows)
        components = tuple(
            repo.resolve(CostComponentEstimate, i)
            for row in rows
            for i in repo.resolve(TotalCostEstimate, row.total_cost_id).component_ids
        )
        assert result.state is CostResultState.AVAILABLE
        evidence[:15] = [
            s.source_ids,
            s.exposure_rule.fingerprint,
            s.exposure_rule.initial_policy.value,
            fixed_s.fingerprint,
            tuple(
                i.fingerprint
                for i in f.inputs
                if i.role in (CostInputRole.BID, CostInputRole.ASK)
            ),
            next(
                c.fingerprint
                for c in s.components
                if c.component is CostComponentType.EXPLICIT_FEE
            ),
            slip.fingerprint,
            impact.fingerprint,
            provider_s.fingerprint,
            s.fingerprint,
            ex_post.fingerprint,
            result.path_id,
            tuple(c.trade_delta for c in changes),
            result.turnover,
            tuple(r.gross_contribution for r in rows),
        ]
        for idx, kind in enumerate(
            (
                CostComponentType.SPREAD,
                CostComponentType.EXPLICIT_FEE,
                CostComponentType.SLIPPAGE,
                CostComponentType.MARKET_IMPACT,
            ),
            15,
        ):
            evidence[idx] = tuple(
                c.amount
                for c in components
                if repo.resolve(CostComponentSpec, c.component_id).component is kind
            )
        evidence[19:22] = [
            tuple(r.total_cost for r in rows),
            tuple(r.net_contribution for r in rows),
            result.fingerprint,
        ]
        evidence[22] = engine.breakeven(result.fingerprint, 100).fingerprint
        evidence[23] = tuple(
            engine.breakeven(result.fingerprint, 100, c.fingerprint).fingerprint
            for c in (spread, slip, impact)
        )
        evidence[24] = engine.sensitivity(
            result.fingerprint, cost_grid.fingerprint, 100
        ).fingerprint
        evidence[25] = engine.sensitivity(
            result.fingerprint, impact_grid.fingerprint, 100
        ).fingerprint
        comparison = engine.compare(
            result.fingerprint, results[point.fingerprint].fingerprint, 100
        )
        assert comparison.state is CostResultState.AVAILABLE
        evidence[26] = comparison.fingerprint
        cohorts = build_cohorts(repo, upstream, reverse)
        definitions = (
            *cohorts.environment_set.definitions,
            *upstream.environment_set.definitions,
        )
        memberships = (*cohorts.membership_ids, *upstream.membership_ids)
        requests = tuple(
            (
                d.fingerprint,
                tuple(
                    i
                    for i in memberships
                    if repo.get(EnvironmentMembership, i).environment_id == d.fingerprint
                ),
            )
            for d in definitions
        )
        cohort_results = engine.cohorts(
            result.fingerprint, tuple(reversed(requests)) if reverse else requests, 100
        )
        for idx, kinds in (
            (27, ("event",)),
            (28, ("regime",)),
            (29, ("sector", "industry", "universe")),
            (30, ("time_window",)),
        ):
            evidence[idx] = tuple(
                c.fingerprint
                for c in cohort_results
                if next(d for d in definitions if d.fingerprint == c.environment_id).kind.value
                in kinds
            )
            assert evidence[idx]
        horizon_results = []
        for metric in horizon_analyses(repo):
            spec = repo.get(StabilityAnalysisSpec, metric.spec_id)
            hs, _ = declare_scenario(repo, spec, reverse)
            horizon_results.append(assess(engine, hs, metric.truth_cutoff_ns)[2])
        assert len(horizon_results) == 2
        evidence[31] = tuple(r.fingerprint for r in horizon_results)
        test_ids = native_forecasts(repo, upstream.upstream, partition=Partition.TEST)
        test_samples = tuple(
            s.fingerprint for s in repo.partition_samples(s.fold_id, Partition.TEST)
        )
        ts, _ = declare_scenario(
            repo,
            replace(upstream.spec, forecast_ids=test_ids, sample_ids=test_samples),
            reverse,
        )
        test_path, test_totals, test_result = assess(
            engine, ts, test_identity="frozen-cost-test"
        )
        before_test = canonical_json(ts)
        test_sample = repo.get(ResearchSample, min(ts.sample_ids))
        assert test_sample.target_id is not None
        test_truth = repo.get(TargetVintage, test_sample.target_id)
        assert test_truth.endpoint_bar_id is not None
        bar_id = test_truth.endpoint_bar_id
        bar = repo.get(TargetBar, bar_id)
        with repo.transaction():
            repo.put(replace(bar, close=(bar.close or 0) + 999, predecessor_id=bar_id))
        assert canonical_json(repo.resolve(type(ts), ts.fingerprint)) == before_test
        assert engine.estimate(ts.fingerprint, 100) == (test_path, test_totals)
        try:
            engine.declare(replace(ts, scenario_id="post-test-tuning", declared_ns=100))
        except ContractError:
            pass
        else:
            raise AssertionError("TEST must not choose new settings")
        evidence[32] = test_result.fingerprint
        causal_sources = upstream.upstream.upstream.ids("gaussian")
        metadata_s = subset_source(repo, s, causal_sources, "origin60-metadata")
        engine.declare(metadata_s)
        with repo.feature_only():
            _, pre = engine.estimate(metadata_s.fingerprint, 60)
            for total in pre:
                change = repo.resolve(ResearchExposureChange, total.change_id)
                assert engine.metadata(total.fingerprint, change.origin) == total
        evidence[33] = tuple(t.fingerprint for t in pre)
        before = canonical_json(result)
        old = min(
            (i for i in f.inputs if i.role is CostInputRole.MODEL_VALUE and i.as_of_ns == 40),
            key=lambda i: i.fingerprint,
        )
        sample = next(
            sample
            for sample in s.sample_ids
            if (v := repo.get(ResearchSample, sample)).origin is not None
            and v.origin.instrument == old.security
            and v.timestamp_ns == old.as_of_ns
        )
        corrected = neutral_input(
            repo.get(ResearchSample, sample),
            old.component,
            old.role,
            (old.value or 0) + 100,
            old.unit,
            late_ns=50,
            revision="correction2",
            horizon_id=old.horizon_id,
        )
        engine.publish_input(corrected)
        revised = replace(
            corrected_input(s, old.fingerprint, corrected), timing=CostTiming.EX_POST_RESEARCH
        )
        updated = assess(engine, revised)[2]
        assert updated.fingerprint != result.fingerprint
        assert canonical_json(repo.get_any(result.fingerprint)) == before
        evidence[34:37] = [corrected.fingerprint, result.fingerprint, updated.fingerprint]
        audit = engine.audit(comparison.fingerprint)
        assert len(audit.node_ids) <= repo.cost_research_bounds.audit_nodes
        evidence[39] = audit.fingerprint
        require(path_value.fingerprint == result.path_id, "demo exact path")
        identities = tuple(
            r[0]
            for r in repo._connection.execute(
                "SELECT fingerprint FROM cost_artifacts ORDER BY fingerprint"
            )
        )
        with repo.read_snapshot(), repo.validation_cache():
            before_all = tuple(canonical_json(repo.get_any(i)) for i in identities)
    with CostResearchRepository(path) as repo:
        with repo.read_snapshot(), repo.validation_cache():
            assert before_all == tuple(canonical_json(repo.get_any(i)) for i in identities)
        assert assess(CostResearchEngine(repo), s)[2] == result
    evidence[37] = len(identities)
    evidence[38] = result.fingerprint
    assert len(STEPS) == len(evidence) == 40 and all(v is not None for v in evidence)
    return {
        "engine": "0.19.0",
        "store": "1.18",
        "schema": "1.0",
        "steps": [
            {"step": i + 1, "action": action, "state": "PASS", "evidence": value}
            for i, (action, value) in enumerate(zip(STEPS, evidence, strict=True))
        ],
        "gross_sum": result.gross_sum,
        "cost_sum": result.total_cost_sum,
        "net_sum": result.net_sum,
        "claims": "Hypothetical arithmetic research contributions; no executable fills, "
        "live PnL, capacity, portfolio or profitability proof.",
    }


def main() -> None:
    with TemporaryDirectory(prefix="afre18-demo-") as folder:
        print(json.dumps(run(Path(folder) / "demo.sqlite"), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
