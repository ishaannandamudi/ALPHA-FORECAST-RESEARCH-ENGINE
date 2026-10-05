"""Bounded offline evidence workflow and separate bulk window kernel; no production SLA."""

import json
import statistics
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.cross_sectional import CrossSectionEngine
from afre.event_conditioned import (
    EventEngine,
    EventModelFamily,
    EventOverlapPolicy,
    EventRelation,
    EventRepository,
)
from afre.event_conditioned.artifacts import (
    EventConditionedForecast,
    EventConditionedObservation,
)
from afre.event_conditioned.windows import window_distance
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import DesignMatrix
from examples.cross_sectional_demo import external
from examples.event_conditioned_demo import build_fixture, build_linear_fixture, event


def main() -> None:
    timings: dict[str, float] = {}
    with TemporaryDirectory() as folder:
        path = Path(folder) / "research.sqlite"
        start = perf_counter()
        with EventRepository(path) as repo:
            f = build_fixture(repo)
            timings["causal_fixture_and_initial_fit_seconds"] = perf_counter() - start
            engine = EventEngine(repo)
            p = next(
                repo.get(EventConditionedForecast, i)
                for i in f.forecast_ids
                if repo.get(EventConditionedForecast, i).event_ids
            )
            o = repo.get(EventConditionedObservation, p.observation_id)
            sample = repo.get(ResearchSample, o.sample_id)
            many = tuple(event(sample, "benchmark:" + str(i), at=59) for i in range(100))
            start = perf_counter()
            ids = tuple(engine.publish_event(e) for e in many)
            timings["event_persistence_seconds"] = perf_counter() - start
            spec = replace(
                f.spec,
                window=replace(
                    f.spec.window, relation=EventRelation.POST_EVENT, post_maximum_age_ns=10
                ),
                overlap=EventOverlapPolicy.ALL_EVENTS_SEPARATE,
            )
            start = perf_counter()
            count = sum(
                window_distance(e, spec.window, t) is not None
                for t in range(50, 550)
                for e in many
            )
            timings["window_kernel_50000_checks_seconds"] = perf_counter() - start
            start = perf_counter()
            observations = engine.observe(spec, o.sample_id, ids)
            timings["matching_and_100_observation_publication_seconds"] = perf_counter() - start
            assert len(observations) == 100
            start = perf_counter()
            engine.observe(
                replace(spec, overlap=EventOverlapPolicy.NEAREST_EVENT), o.sample_id, ids
            )
            timings["nearest_overlap_seconds"] = perf_counter() - start
            signal = external(sample.security, 60, 0.2, 60)
            CrossSectionEngine(repo).publish_external(signal)
            reaction_spec = replace(
                spec,
                family=EventModelFamily.EVENT_FEATURE_LINEAR,
                reaction_specs=(f.upstream.spec.score,),
            )
            start = perf_counter()
            reaction_observation = engine.observe(
                reaction_spec, o.sample_id, ids[:1], (signal.fingerprint,)
            )[0]
            assert reaction_observation.reaction_ids == (signal.fingerprint,)
            timings["reaction_lookup_and_observation_seconds"] = perf_counter() - start
            start = perf_counter()
            engine.fit(f.spec, f.training_observation_ids, 40, 40, 40)
            timings["class_fit_replay_seconds"] = perf_counter() - start
            start = perf_counter()
            materiality = build_linear_fixture(
                repo, f, "materiality", EventModelFamily.MATERIALITY_LINEAR
            )
            surprise = build_linear_fixture(
                repo, f, "surprise", EventModelFamily.SURPRISE_LINEAR
            )
            timings["two_linear_fit_and_forecast_workflows_seconds"] = perf_counter() - start
            start = perf_counter()
            for i in f.forecast_ids:
                forecast = repo.get(EventConditionedForecast, i)
                engine.forecast(
                    forecast.model_id,
                    forecast.observation_id,
                    forecast.base_forecast_id,
                    60,
                    forecast.base_probability_id,
                )
            timings["four_forecast_replay_seconds"] = perf_counter() - start
            start = perf_counter()
            evaluation = engine.evaluate(f.forecast_ids, 100, 100)
            timings["matched_evaluation_seconds"] = perf_counter() - start
            start = perf_counter()
            rank = engine.rank(f.upstream.spec, f.forecast_ids, f.upstream.group_refs)
            engine.evaluate_rank(rank.fingerprint, 100, 100)
            timings["cross_section_rank_and_IC_seconds"] = perf_counter() - start
            start = perf_counter()
            audit = engine.audit_lineage(evaluation.fingerprint)
            timings["bounded_lineage_seconds"] = perf_counter() - start
            start = perf_counter()
            artifact_count = repo.audit()
            timings["full_repository_audit_seconds"] = perf_counter() - start
            oracle_errors: list[float] = []
            rows = {
                r.sample_id: r.response for r in repo.get(DesignMatrix, f.model.matrix_id).rows
            }
            for fixture, key in ((materiality, "materiality"), (surprise, "surprise")):
                admitted = tuple(
                    repo.get(EventConditionedObservation, i)
                    for i in fixture.training_observation_ids
                )
                oracle = statistics.linear_regression(
                    [dict(v.values)[key] for v in admitted],
                    [rows[v.sample_id] for v in admitted],
                )
                oracle_errors.extend(
                    abs(a - b)
                    for a, b in zip(
                        fixture.model.coefficients,
                        (oracle.intercept, oracle.slope),
                        strict=True,
                    )
                )
            before = canonical_json(evaluation)
        storage_bytes = path.stat().st_size
        start = perf_counter()
        with EventRepository(path) as repo:
            assert canonical_json(repo.get_any(evaluation.fingerprint)) == before
            repo.audit()
        timings["restart_and_full_audit_seconds"] = perf_counter() - start
    output = {
        "engine": "0.11.0",
        "store": "1.10",
        "sqlite_user_version": 11,
        "workload": {
            "additional_event_references": 100,
            "bulk_window_checks": 50000,
            "overlap_observations": 100,
            "deployment_forecasts": 4,
            "linear_families": 2,
            "window_matches": count,
        },
        "timings": timings,
        "storage_bytes": storage_bytes,
        "artifact_count": artifact_count,
        "audit_nodes": len(audit.evidence_ids),
        "maximum_linear_oracle_absolute_error": max(oracle_errors),
        "interpretation": (
            "Synthetic bounded offline profile; full causal workflow and bulk window kernel "
            "measured separately; no production SLA or profitability claim."
        ),
    }
    encoded = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
