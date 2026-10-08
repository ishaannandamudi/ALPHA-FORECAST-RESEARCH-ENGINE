"""Bounded native workflow, separate arithmetic workload and independent cost oracles."""

import json
import math
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TypeVar

from afre.costs import (
    CostResearchEngine,
    CostResearchRepository,
    CostSensitivitySpec,
    CostTiming,
)
from afre.costs.components import component_for
from afre.costs.exposures import path_for
from afre.costs.schema import CostComponentType
from afre.costs.totals import total_from
from afre.costs.turnover import turnover
from afre.invariance import EnvironmentMembership
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from afre.target_engine.models import TargetVintage
from examples.costs_fixture import build_fixture
from examples.costs_workflow import assess
from examples.invariance_cohorts import build_cohorts

T = TypeVar("T")


def timed(fn: Callable[[], T]) -> tuple[T, float]:
    started = perf_counter()
    result = fn()
    return result, perf_counter() - started


def profile() -> dict[str, object]:
    with TemporaryDirectory(prefix="afre18-profile-") as folder:
        path = Path(folder) / "profile.sqlite"
        with CostResearchRepository(path) as repo:
            f, fixture_s = timed(lambda: build_fixture(repo))
            s = f.scenario
            e = CostResearchEngine(repo)
            with repo.feature_only(), repo.read_snapshot(), repo.validation_cache():
                (changes, _), exposure_s = timed(lambda: path_for(repo, s.fingerprint, 100))
                trades, turnover_s = timed(lambda: turnover(changes))
                components, component_s = timed(
                    lambda: tuple(
                        component_for(repo, c, d.fingerprint)
                        for c in changes
                        for d in s.components
                    )
                )
                _, total_s = timed(
                    lambda: tuple(
                        total_from(
                            s, c, tuple(v for v in components if v.change_id == c.fingerprint)
                        )
                        for c in changes
                    )
                )
            (p, ts), publication_s = timed(lambda: e.estimate(s.fingerprint, 100))
            result, evaluation_s = timed(
                lambda: e.evaluate(p.fingerprint, tuple(t.fingerprint for t in ts), 100, 100)
            )
            _, scenario_s = timed(
                lambda: assess(
                    e,
                    replace(
                        s, scenario_id="profile-ex-post", timing=CostTiming.EX_POST_RESEARCH
                    ),
                )
            )
            slip = next(c for c in s.components if c.component is CostComponentType.SLIPPAGE)
            impact = next(
                c for c in s.components if c.component is CostComponentType.MARKET_IMPACT
            )
            grid = CostSensitivitySpec(
                s.fingerprint, slip.fingerprint, (0.0, 1.0, 2.0, 5.0, 10.0), (), (1.0, 2.0), 40
            )
            participation = CostSensitivitySpec(
                s.fingerprint,
                impact.fingerprint,
                (0.0, 10.0, 20.0),
                (0.0, 0.01, 0.1),
                (1.0,),
                40,
            )
            for g in (grid, participation):
                e.register_sensitivity(g)
            curves, sensitivity_s = timed(
                lambda: tuple(
                    e.sensitivity(result.fingerprint, g.fingerprint, 100)
                    for g in (grid, participation)
                )
            )
            diagnostics, break_s = timed(
                lambda: tuple(
                    e.breakeven(result.fingerprint, 100, c)
                    for c in (None, *(c.fingerprint for c in s.components))
                )
            )
            cohorts = build_cohorts(repo, f.upstream)
            requests = tuple(
                (
                    d.fingerprint,
                    tuple(
                        i
                        for i in cohorts.membership_ids
                        if repo.get(EnvironmentMembership, i).environment_id == d.fingerprint
                    ),
                )
                for d in cohorts.environment_set.definitions
            )
            cohort_results, cohort_s = timed(
                lambda: e.cohorts(result.fingerprint, requests, 100)
            )
            audit, audit_s = timed(lambda: e.audit(cohort_results[0].fingerprint))
            _, persistence_s = timed(
                lambda: e._publish((result, *curves, *diagnostics, *cohort_results))
            )
            specs = {d.fingerprint: d for d in s.components}
            errors: dict[str, float] = {}
            for c in changes:
                delta = abs(c.trade_delta)
                expected = {
                    CostComponentType.SPREAD: delta * 0.0002,
                    CostComponentType.EXPLICIT_FEE: delta * 0.0001,
                    CostComponentType.SLIPPAGE: delta * 0.0001,
                    CostComponentType.MARKET_IMPACT: delta * 20 * (delta * 0.01) * 0.0001,
                    CostComponentType.CUSTOM_COST: delta * 0.00005,
                }
                for component in (v for v in components if v.change_id == c.fingerprint):
                    key = specs[component.component_id].component
                    assert component.amount is not None
                    errors[key.value] = max(
                        errors.get(key.value, 0), abs(component.amount - expected[key])
                    )
            gross_values = []
            for c in changes:
                sample = repo.get(ResearchSample, c.sample_id)
                assert sample.target_id is not None
                truth = repo.get(TargetVintage, sample.target_id)
                assert truth.value is not None
                gross_values.append(c.exposure * truth.value)
            oracle_gross = math.fsum(gross_values)
            oracle_cost = math.fsum(
                abs(c.trade_delta)
                * (
                    0.0002
                    + 0.0001
                    + 0.0001
                    + 0.00005
                    + 20 * (abs(c.trade_delta) * 0.01) * 0.0001
                )
                for c in changes
            )
            assert (
                result.gross_sum is not None
                and result.total_cost_sum is not None
                and result.net_sum is not None
            )
            errors["gross_sum"] = abs(result.gross_sum - oracle_gross)
            errors["total_sum"] = abs(result.total_cost_sum - oracle_cost)
            errors["net_sum"] = abs(result.net_sum - (oracle_gross - oracle_cost))
            errors["gross_mean"] = abs((result.gross_mean or 0) - oracle_gross / len(changes))
            errors["net_mean"] = abs(
                (result.net_mean or 0) - (oracle_gross - oracle_cost) / len(changes)
            )
            errors["break_even_bps"] = abs(
                (diagnostics[0].threshold or 0) - oracle_gross / (trades * 0.0001)
            )
            for point in curves[0].points:
                m = point.turnover_multiplier
                oracle = trades * m * (0.00035 + point.rate * 0.0001) + math.fsum(
                    abs(c.trade_delta) ** 2 * 20 * 0.01 * 0.0001 * m**2 for c in changes
                )
                assert point.net_sum is not None
                errors["cost_curve"] = max(
                    errors.get("cost_curve", 0), abs(point.net_sum - (oracle_gross - oracle))
                )
            assert max(errors.values()) < 1e-12
            identities = tuple(
                r[0]
                for r in repo._connection.execute(
                    "SELECT fingerprint FROM cost_artifacts ORDER BY fingerprint"
                )
            )
            with repo.read_snapshot(), repo.validation_cache():
                before = tuple(canonical_json(repo.get_any(i)) for i in identities)
            payload = repo._connection.execute(
                "SELECT sum(length(payload)) FROM cost_artifacts"
            ).fetchone()[0]
        started = perf_counter()
        with (
            CostResearchRepository(path) as repo,
            repo.read_snapshot(),
            repo.validation_cache(),
        ):
            assert before == tuple(canonical_json(repo.get_any(i)) for i in identities)
        restart_s = perf_counter() - started
        quantities = tuple((i % 5 - 2) / 2 for i in range(2000))
        _, arithmetic_s = timed(
            lambda: tuple(
                math.fsum(abs(v) * (0.00045 + 0.002 * abs(v) * 0.01) for v in quantities)
                for _ in range(32)
            )
        )
        return {
            "engine": "0.19.0",
            "store": "1.18",
            "sqlite_user_version": 19,
            "schema": "1.0",
            "native_samples_per_scenario": 12,
            "native_scenarios": 2,
            "native_sample_evaluations": 24,
            "components_per_sample": 5,
            "cohorts": len(cohort_results),
            "grid_points": sum(len(c.points) for c in curves),
            "audit_nodes": len(audit.node_ids),
            "cost_artifacts": len(identities),
            "canonical_cost_payload_bytes": payload,
            "sqlite_bytes": path.stat().st_size,
            "seconds": {
                "upstream_fixture_and_declaration": fixture_s,
                "exposure": exposure_s,
                "turnover": turnover_s,
                "component_costs": component_s,
                "total_costs": total_s,
                "snapshot_estimation_and_publication": publication_s,
                "gross_net_evaluation": evaluation_s,
                "second_scenario": scenario_s,
                "break_even": break_s,
                "sensitivity": sensitivity_s,
                "cohorts": cohort_s,
                "audit": audit_s,
                "idempotent_persistence": persistence_s,
                "restart": restart_s,
                "separate_32_by_2000_arithmetic": arithmetic_s,
            },
            "maximum_numerical_error": errors,
            "limits": "Bounded synthetic offline measurement. Separate 2000-row arithmetic "
            "workload is not a native dataset, fill simulation, capacity estimate "
            "or production SLA.",
        }


if __name__ == "__main__":
    print(json.dumps(profile(), sort_keys=True, indent=2))
