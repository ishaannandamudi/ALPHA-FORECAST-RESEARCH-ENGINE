"""Separate bounded timings and independent elementary score oracles; no production SLA."""

import json
from dataclasses import replace
from math import erf, exp, log, pi, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.challenger import (
    ChallengeEngine,
    ChallengeRepository,
    ParticipantReference,
)
from afre.challenger import (
    ChallengeMetric as M,
)
from afre.challenger.assessments import comparison_for, promotion_for
from afre.challenger.engine import run_for
from afre.challenger.matching import common_for
from afre.challenger.metrics import metric_for
from examples.challenge_context import cost_context_for, health_context_for
from examples.challenge_rollback import rollback_challenge
from examples.challenger_fixture import build_challenge_fixture, evidence_for, program_for
from examples.health_native import build_native, matching_family


def profile(directory: Path) -> dict[str, object]:
    path = directory / "challenge-profile.sqlite"
    timings: dict[str, float] = {}
    with ChallengeRepository(path) as repo:
        started = perf_counter()
        f = build_challenge_fixture(repo)
        timings["fixture_seconds"] = perf_counter() - started
        engine = ChallengeEngine(repo)
        started = perf_counter()
        with repo.read_snapshot(), repo.validation_cache():
            for p in f.participants:
                repo.resolve(ParticipantReference, p.fingerprint)
        timings["participant_resolution_seconds"] = perf_counter() - started
        program, rules = program_for(f, (M.MAE, M.MSE, M.RMSE, M.CRPS, M.NLL, M.IC))
        rules = tuple(
            r
            for r in rules
            if r.request_id == next(q.fingerprint for q in program.requests if q.kind is M.MAE)
        )
        program = replace(program, promotion_criterion_ids=tuple(r.fingerprint for r in rules))
        engine.declare(program, rules)
        started = perf_counter()
        evidence = evidence_for(repo, f, program)
        timings["shadow_construction_seconds"] = perf_counter() - started
        engine.evidence(evidence)
        with repo.read_snapshot(), repo.validation_cache(), repo.pending_results():
            started = perf_counter()
            common = common_for(repo, program, evidence)
            timings["matching_seconds"] = perf_counter() - started
            repo.stage_result(common)
            started = perf_counter()
            metrics = tuple(
                metric_for(repo, program, common, p, r)
                for p in (program.champion_id, *program.challenger_ids)
                for r in program.requests
            )
            timings["metric_evaluation_seconds"] = perf_counter() - started
            for m in metrics:
                repo.stage_result(m)
            by_key = {(m.participant_id, m.request_id): m for m in metrics}
            started = perf_counter()
            comparisons = tuple(
                comparison_for(
                    program,
                    by_key[program.champion_id, r.fingerprint],
                    by_key[p, r.fingerprint],
                )
                for p in program.challenger_ids
                for r in program.requests
            )
            timings["comparison_seconds"] = perf_counter() - started
            for comparison in comparisons:
                repo.stage_result(comparison)
            started = perf_counter()
            promotions = tuple(
                promotion_for(
                    repo,
                    program,
                    evidence,
                    p,
                    tuple(c for c in comparisons if c.challenger_id == p),
                )
                for p in program.challenger_ids
            )
            timings["criteria_evaluation_seconds"] = perf_counter() - started
            run = run_for(program, evidence, common, metrics, comparisons, promotions, ())
        started = perf_counter()
        engine.publish((common, *metrics, *comparisons, *promotions, run))
        timings["persistence_seconds"] = perf_counter() - started
        started = perf_counter()
        health = health_context_for(repo, f, program)
        cost_program, cost_rules = program_for(f, (M.GROSS_EDGE, M.COST, M.NET_EDGE))
        plan, costs = cost_context_for(repo, f, cost_program)
        cost_program = replace(
            cost_program,
            cost_plan_id=plan.fingerprint,
            health_participant_ids=(program.champion_id, *program.challenger_ids),
        )
        engine.declare(cost_program, cost_rules)
        cost_evidence = engine.evidence(
            replace(
                evidence_for(repo, f, cost_program), cost_bindings=costs, health_bindings=health
            )
        )
        cost_run = engine.evaluate(cost_evidence.fingerprint)
        timings["health_cost_context_seconds"] = perf_counter() - started
        started = perf_counter()
        audit = engine.audit(run.fingerprint)
        timings["audit_seconds"] = perf_counter() - started
        errors = []
        champion = {m.kind: m for m in metrics if m.participant_id == program.champion_id}
        expected = {
            M.MAE: 0.1,
            M.MSE: 0.01,
            M.RMSE: 0.1,
            M.NLL: log(0.05 * sqrt(2 * pi)) + 2.0,
            M.CRPS: 0.05 * (2 * erf(2 / sqrt(2)) + sqrt(2 / pi) * exp(-2) - 1 / sqrt(pi)),
            M.IC: 1.0,
        }
        for kind, value in expected.items():
            actual = champion[kind].value
            assert actual is not None
            errors.append((kind.value, abs(actual - value)))
        counts = dict(
            repo._connection.execute("SELECT kind,count(*) FROM ch_records GROUP BY kind")
        )
    started = perf_counter()
    with ChallengeRepository(path) as reopened:
        assert reopened.resolve(type(run), run.fingerprint) == run
        assert reopened.resolve(type(cost_run), cost_run.fingerprint) == cost_run
    timings["restart_seconds"] = perf_counter() - started
    started = perf_counter()
    with ChallengeRepository(directory / "rollback-profile.sqlite") as native_repo:
        native = build_native(native_repo)
        sources = native.upstream.upstream.upstream
        rollback = rollback_challenge(
            native_repo,
            matching_family(native_repo, sources.ids("point")),
            matching_family(native_repo, sources.ids("gaussian")),
        )
        assert rollback.rollback_ids
    timings["rollback_native_fixture_seconds"] = perf_counter() - started
    started = perf_counter()
    storage_bytes = path.stat().st_size
    timings["storage_measurement_seconds"] = perf_counter() - started
    assert max(v for _, v in errors) < 1e-10
    return {
        "boundary": "bounded AFRE23 offline synthetic research; no production SLA",
        "timings": timings,
        "counts": counts,
        "champions_per_program": 1,
        "challengers": 2,
        "matched_samples": len(common.assignments),
        "audit_nodes": len(audit.node_ids),
        "audit_bytes": audit.serialized_bytes,
        "sqlite_bytes": storage_bytes,
        "maximum_numerical_error": max(v for _, v in errors),
        "numerical_errors": dict(errors),
    }


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        result = profile(Path(directory))
    print(json.dumps(result, sort_keys=True, indent=2))
