"""Measured bounded native workflow plus a separate 2,000-slot arithmetic profile."""

import json
import platform
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypeVar
from unittest.mock import patch

from afre.multiple_testing import (
    CorrectionMethod as C,
)
from afre.multiple_testing import (
    FamilyCompleteness,
    HypothesisDirection,
    MultipleTestingEngine,
    MultipleTestingRepository,
    TrialState,
    adjust_pvalues,
    fair_sign_pvalue,
)
from afre.multiple_testing.repository import TESTING_TYPES
from afre.schema import Artifact
from examples.costs_fixture import build_fixture as native_fixture
from examples.multiple_testing_demo import payload_digest
from examples.multiple_testing_fixture import declare_fixture

A = TypeVar("A")
R = TypeVar("R")


def profile(path: Path) -> dict[str, object]:
    timings: dict[str, float] = {}

    def measured(
        function: Callable[[MultipleTestingEngine, A], R], name: str
    ) -> Callable[[MultipleTestingEngine, A], R]:
        def invoke(engine: MultipleTestingEngine, value: A) -> R:
            start = time.perf_counter()
            try:
                return function(engine, value)
            finally:
                timings[name] = timings.get(name, 0.0) + time.perf_counter() - start

        return invoke

    original_put = MultipleTestingRepository.put

    def measured_put(owner: MultipleTestingRepository, value: Artifact) -> str:
        start = time.perf_counter()
        identity = original_put(owner, value)
        if type(value) in TESTING_TYPES:
            key = "persistence_admission_and_insert_seconds"
            timings[key] = timings.get(key, 0.0) + time.perf_counter() - start
        return identity

    started = time.perf_counter()
    with (
        MultipleTestingRepository(path) as repo,
        patch.object(MultipleTestingRepository, "put", measured_put),
    ):
        timings["store_open_migrate_seconds"] = time.perf_counter() - started
        started = time.perf_counter()
        native = native_fixture(repo)
        timings["native_source_construction_seconds"] = time.perf_counter() - started
        started = time.perf_counter()
        with (
            patch.object(
                MultipleTestingEngine,
                "hypothesis",
                measured(MultipleTestingEngine.hypothesis, "metadata_registration_seconds"),
            ),
            patch.object(
                MultipleTestingEngine,
                "plan",
                measured(MultipleTestingEngine.plan, "metadata_registration_seconds"),
            ),
            patch.object(
                MultipleTestingEngine,
                "family",
                measured(
                    MultipleTestingEngine.family, "family_construction_publication_seconds"
                ),
            ),
        ):
            f = declare_fixture(repo, native)
        timings["native_context_and_declarations_seconds"] = time.perf_counter() - started
        e = MultipleTestingEngine(repo)
        trials = []
        results, cutoffs = dict(f.cost_results), dict(f.cutoffs)
        started = time.perf_counter()
        for p in f.plans:
            at = cutoffs.get(p.fingerprint, 100)
            state = (
                TrialState.FAILED
                if p.attempt_key == "failed"
                else TrialState.UNAVAILABLE
                if p.attempt_key == "unavailable"
                else TrialState.COMPLETED
            )
            trials.append(
                e.complete(
                    p.fingerprint,
                    f.family.fingerprint,
                    at,
                    at,
                    state=state,
                    native_result_ids=(results[p.fingerprint],)
                    if p.fingerprint in results
                    else (),
                    test_identity="profile-frozen-test"
                    if p.attempt_key.startswith("test-")
                    else None,
                )
            )
        timings["trial_calculation_and_publication_seconds"] = time.perf_counter() - started
        at = max(t.completed_ns for t in trials)
        started = time.perf_counter()
        outputs = e.analyze(
            f.family.fingerprint,
            tuple(t.fingerprint for t in trials),
            FamilyCompleteness.COMPLETE,
            at,
            at,
        )
        timings["family_adjustment_and_atomic_publication_seconds"] = (
            time.perf_counter() - started
        )
        started = time.perf_counter()
        registry = e.registry(at, at)
        e.overfitting(registry.fingerprint, at)
        timings["registry_and_opportunity_diagnostic_seconds"] = time.perf_counter() - started
        started = time.perf_counter()
        audit = e.audit(outputs[0].fingerprint)
        timings["unified_audit_and_publication_seconds"] = time.perf_counter() - started
        started = time.perf_counter()
        digest = payload_digest(repo)
        timings["semantic_payload_replay_seconds"] = time.perf_counter() - started
        artifacts = repo._connection.execute("SELECT count(*) FROM mt_artifacts").fetchone()[0]
        payload_bytes = repo._connection.execute(
            "SELECT sum(length(CAST(payload AS BLOB))) FROM mt_artifacts"
        ).fetchone()[0]
    started = time.perf_counter()
    with MultipleTestingRepository(path) as restarted:
        assert payload_digest(restarted) == digest
    timings["restart_and_semantic_replay_seconds"] = time.perf_counter() - started
    started = time.perf_counter()
    arithmetic = tuple((str(i), float((i * 37) % 2001) / 2001) for i in range(2000))
    for method in C:
        adjust_pvalues(arithmetic, method)
    timings["separate_2000_slot_four_method_arithmetic_seconds"] = time.perf_counter() - started
    fixtures = (("a", 0.001), ("b", 0.01), ("c", 0.02), ("d", 0.5), ("e", None))
    expected = {
        C.BONFERRONI: (0.005, 0.05, 0.1, 1.0, 1.0),
        C.HOLM: (0.005, 0.04, 0.06, 1.0, 1.0),
        C.BENJAMINI_HOCHBERG: (0.005, 0.025, 1 / 30, 0.625, 1.0),
        C.BENJAMINI_YEKUTIELI: (137 / 12000, 137 / 2400, 137 / 1800, 1.0, 1.0),
    }
    errors = [
        abs(p - target)
        for method, targets in expected.items()
        for (_, p, _), target in zip(adjust_pvalues(fixtures, method), targets, strict=True)
    ]
    errors.append(abs(fair_sign_pvalue(5, 5, HypothesisDirection.GREATER) - 1 / 32))
    return {
        "phase": "AFRE-19",
        "engine": "0.20.0",
        "store": "1.19",
        "sqlite_user_version": 20,
        "python": platform.python_version(),
        "network": "offline",
        "timings": timings,
        "timing_note": (
            "registration/family substage times overlap the inclusive declaration stage"
        ),
        "native_trial_count": len(trials),
        "family_size": len(f.family.plan_ids),
        "native_phases": list(range(5, 19)),
        "actual_horizons": "1h and 1d",
        "environment_opportunities": 2,
        "cost_scenario_opportunities": 2,
        "correction_reports": len(outputs),
        "artifacts": artifacts,
        "payload_bytes": payload_bytes,
        "sqlite_bytes": path.stat().st_size,
        "audit_nodes": len(audit.node_ids),
        "max_numerical_fixture_error": max(errors),
        "digest": digest,
        "limits": (
            "25 native opportunities; 2000-slot arithmetic measured separately; "
            "no capacity extrapolation"
        ),
    }


def main() -> None:
    with TemporaryDirectory() as folder:
        print(json.dumps(profile(Path(folder) / "profile.sqlite"), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
