"""Offline causal store profile plus a separate 5,000-observation numerical workload."""

import cProfile
import io
import json
import pstats
from collections.abc import Callable
from dataclasses import replace
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TypeVar

from afre.calibration import (
    CalibrationDriftSpec,
    CalibrationEngine,
    CalibrationMethod,
    CalibrationObservationSet,
    CalibrationRequest,
    DriftMetric,
)
from afre.calibration.artifacts import CalibrationObservation, IntervalValue
from afre.calibration.conformal import conformal_rank, scores_for
from afre.calibration.definitions import CalibrationSpec
from afre.calibration.diagnostics import diagnostics_for
from afre.calibration.fitting import transformations
from afre.calibration.isotonic import pav
from afre.calibration.quantile import offset_for
from afre.calibration.samples import observations_for
from afre.probabilistic import (
    QuantileValue,
    ThresholdComparison,
    ThresholdProbability,
    ThresholdRequest,
)
from afre.serialization import canonical_json
from examples.calibration_demo import (
    CalibrationDemoRepository,
    build_calibration_fixture,
    method_spec,
)

T = TypeVar("T")


def timed(times: dict[str, float], name: str, operation: Callable[[], T]) -> T:
    start = perf_counter()
    result = operation()
    times[name] = perf_counter() - start
    return result


def numerical_errors(
    observations: CalibrationObservationSet, spec: CalibrationSpec
) -> dict[str, float]:
    ids = tuple(f"afre.c_observation:1.0:{i:064x}" for i in range(1, 6))
    blocks = pav(
        (
            (0.1, False, ids[0]),
            (0.2, True, ids[1]),
            (0.2, False, ids[2]),
            (0.3, False, ids[3]),
            (0.8, True, ids[4]),
        )
    )
    event = ThresholdRequest(0.0, ThresholdComparison.GT)
    q = (QuantileValue(0.1, -1.0), QuantileValue(0.5, 0.0), QuantileValue(0.9, 1.0))
    interval = IntervalValue(0.1, 0.9, -1.0, 1.0)
    rows = tuple(
        (y, q, (ThresholdProbability(event, p),), interval)
        for y, p in ((1.0, 0.2), (-1.0, 0.2), (2.0, 0.8), (-2.0, 0.8))
    )
    from afre.calibration import CalibrationBinDefinition

    diagnostics = diagnostics_for(
        rows, rows, CalibrationBinDefinition((0.0, 0.5, 1.0)), "independent-evaluation"
    )
    reliability = diagnostics.raw_events[0]
    coverage = diagnostics.raw_interval
    assert (
        coverage is not None and coverage.coverage is not None and reliability.ece is not None
    )
    base = observations.rows[0]

    def fixture_rows(count: int, first_truth: int) -> tuple[CalibrationObservation, ...]:
        return tuple(
            replace(
                base,
                truth=float(first_truth + i),
                quantiles=q,
                median=0.0,
                sample_id=f"afre.r_sample:1.0:{i:064x}",
                raw_forecast_id=f"afre.p_forecast:1.0:{i:064x}",
            )
            for i in range(count)
        )

    def fixture_set(
        rows: tuple[CalibrationObservation, ...], selected_spec: CalibrationSpec
    ) -> CalibrationObservationSet:
        return CalibrationObservationSet(
            selected_spec.fingerprint,
            tuple(CalibrationRequest(r.raw_forecast_id, r.target_id) for r in rows),
            rows,
            (),
        )

    q_spec = replace(spec, method=CalibrationMethod.QUANTILE_OFFSET)
    q_set = fixture_set(fixture_rows(4, 0), q_spec)
    offset_error = max(
        abs(offset_for(q_spec, q_set, level).offset - reference)
        for level, reference in ((0.1, 1.3), (0.5, 1.5), (0.9, 1.7))
    )
    conformal_spec = replace(
        spec, method=CalibrationMethod.CONFORMAL_ABSOLUTE_RESIDUAL, miscoverage_alpha=0.2
    )
    score_set = scores_for(conformal_spec, fixture_set(fixture_rows(9, 1), conformal_spec))
    return {
        "PAV_rate_abs_error": abs(blocks[1].probability - 1 / 3),
        "type7_offset_abs_error": offset_error,
        "conformal_rank_abs_error": float(abs(conformal_rank(9, 0.2) - 8)),
        "conformal_q_hat_abs_error": abs(score_set.q_hat - 8.0),
        "ECE_abs_error": abs(reliability.ece - 0.3),
        "coverage_abs_error": abs(coverage.coverage - 0.5),
    }


def main() -> None:
    times: dict[str, float] = {}
    profile = cProfile.Profile()
    with TemporaryDirectory(prefix="afre-calibration-profile-") as directory:
        path = Path(directory) / "profile.sqlite"
        with CalibrationDemoRepository(path) as repo:
            fixture = timed(times, "causal_scaffold", lambda: build_calibration_fixture(repo))
            with repo.read_snapshot():
                observations = timed(
                    times,
                    "causal_sample_construction",
                    lambda: observations_for(repo, fixture.spec, fixture.requests),
                )
            # These generated observations test computational kernels only. They are not
            # published or claimed as eligible causal repository evidence.
            events = tuple(ThresholdRequest(0.0, c) for c in ThresholdComparison)
            qs = (QuantileValue(0.1, -0.1), QuantileValue(0.5, 0.0), QuantileValue(0.9, 0.1))
            base = observations.rows[0]
            rows = tuple(
                CalibrationObservation(
                    f"afre.p_forecast:1.0:{i:064x}",
                    f"afre.r_sample:1.0:{i:064x}",
                    base.target_id,
                    base.origin,
                    base.target_definition_id,
                    float(i % 11 - 5) / 100,
                    base.truth_available_ns,
                    base.raw_available_ns,
                    55,
                    qs,
                    tuple(ThresholdProbability(e, (i % 101) / 100) for e in events),
                    0.0,
                    IntervalValue(0.1, 0.9, -0.1, 0.1),
                )
                for i in range(1, 5001)
            )
            from afre.probabilistic import ThresholdDefinition

            synthetic_spec = replace(
                method_spec(fixture, CalibrationMethod.ISOTONIC_PROBABILITY),
                events=ThresholdDefinition(events),
            )
            synthetic = CalibrationObservationSet(
                synthetic_spec.fingerprint,
                tuple(CalibrationRequest(r.raw_forecast_id, r.target_id) for r in rows),
                rows,
                (),
            )
            numeric = timed(
                times,
                "5000_observation_isotonic_diagnostics",
                lambda: transformations(synthetic_spec, synthetic),
            )
            conformal_spec = replace(
                method_spec(fixture, CalibrationMethod.CONFORMAL_ABSOLUTE_RESIDUAL),
                events=ThresholdDefinition(events),
            )
            timed(
                times,
                "5000_observation_conformal_diagnostics",
                lambda: transformations(
                    conformal_spec, replace(synthetic, spec_id=conformal_spec.fingerprint)
                ),
            )
            offset_spec = replace(
                method_spec(fixture, CalibrationMethod.QUANTILE_OFFSET),
                events=ThresholdDefinition(events),
            )
            timed(
                times,
                "5000_observation_quantile_offsets",
                lambda: transformations(
                    offset_spec, replace(synthetic, spec_id=offset_spec.fingerprint)
                ),
            )
            profile.enable()
            engine = CalibrationEngine(repo)
            evaluations = []
            for method in CalibrationMethod:
                run = timed(
                    times,
                    method.value + "_fit_persist_validate",
                    partial(
                        engine.fit, method_spec(fixture, method), fixture.requests, 55, 55, 55
                    ),
                )
                forecasts = timed(
                    times,
                    method.value + "_batch_application_persistence",
                    partial(
                        engine.apply_batch,
                        run.state_id,
                        tuple(p.fingerprint for p in fixture.deployment_raw),
                    ),
                )
                evaluation = timed(
                    times,
                    method.value + "_evaluation_persistence",
                    partial(engine.evaluate, tuple(f.fingerprint for f in forecasts), 75, 75),
                )
                evaluations.append(evaluation)
                timed(
                    times,
                    method.value + "_comparison",
                    partial(
                        engine.compare, evaluation.raw_evaluation_id, evaluation.fingerprint
                    ),
                )
            timed(
                times,
                "rolling_diagnostics_persistence",
                lambda: engine.diagnose_drift(
                    CalibrationDriftSpec(1, 1, DriftMetric.ECE, 0.25),
                    (evaluations[1].fingerprint,),
                ),
            )
            audit = timed(
                times,
                "full_lineage_audit_persistence",
                lambda: engine.calibration_audit(forecasts[0].fingerprint),
            )
            timed(times, "whole_store_semantic_audit", repo.audit)
            profile.disable()
            ids = (run.state_id, forecasts[0].fingerprint, evaluation.fingerprint)
            frozen = tuple(canonical_json(repo.get_any(i)) for i in ids)
            artifact_count = repo._connection.execute(
                "SELECT count(*) FROM c_artifacts"
            ).fetchone()[0]
        started = perf_counter()
        with CalibrationDemoRepository(path) as restarted:
            assert tuple(canonical_json(restarted.get_any(i)) for i in ids) == frozen
        times["restart_and_byte_replay"] = perf_counter() - started
        output = {
            "seconds": times,
            "numerical_observations": 5000,
            "numerical_events": 4,
            "numerical_quantiles": 3,
            "numerical_isotonic_blocks": [len(m.blocks) for m in numeric[0]],
            "causal_calibration_observations": len(observations.rows),
            "causal_deployment_forecasts_per_method": len(forecasts),
            "calibration_artifacts": artifact_count,
            "lineage_nodes": len(audit.evidence_ids),
            "sqlite_bytes": path.stat().st_size,
            "errors": numerical_errors(observations, fixture.spec),
            "workload_boundary": (
                "5000 synthetic kernel observations; separate small fully causal "
                "persistence fixture; no production SLA"
            ),
        }
        print(json.dumps(output, sort_keys=True, indent=2))
        stream = io.StringIO()
        pstats.Stats(profile, stream=stream).sort_stats("cumulative").print_stats(12)
        print(stream.getvalue())


if __name__ == "__main__":
    main()
