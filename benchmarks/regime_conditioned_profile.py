"""Bounded causal workflow and larger independent weighted arithmetic kernels."""

import json
import statistics
import sys
from dataclasses import replace
from math import fsum
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.cross_sectional.artifacts import CrossSectionEvaluation
from afre.regime_conditioned import (
    RegimeConditionedEvaluation,
    RegimeConditionedForecast,
    RegimeConditionedSample,
    RegimeEngine,
    RegimeModelFamily,
    RegimeRepository,
)
from afre.regime_conditioned.memberships import effective_support
from afre.regime_conditioned.transitions import transition_for
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import DesignMatrix, FittedModelArtifact
from examples.regime_conditioned_demo import build_fixture, snapshot, taxonomy


def main() -> None:
    timings: dict[str, float] = {}
    errors: dict[str, float] = {}
    with TemporaryDirectory() as folder:
        path = Path(folder) / "regime.sqlite"
        start = perf_counter()
        with RegimeRepository(path) as repo:
            hard = build_fixture(repo)
            soft = build_fixture(repo, upstream=hard.upstream, soft=True)
            target_mean = build_fixture(
                repo, upstream=hard.upstream, family=RegimeModelFamily.REGIME_TARGET_MEAN
            )
            timings["causal_fixture_hard_soft_initial_fit_seconds"] = perf_counter() - start
            engine = RegimeEngine(repo)
            p = next(
                repo.get(RegimeConditionedForecast, i)
                for i in hard.forecast_ids
                if repo.get(RegimeConditionedForecast, i).regime_snapshot_id
            )
            sample = repo.get(
                ResearchSample, repo.get(RegimeConditionedSample, p.observation_id).sample_id
            )
            tax = taxonomy()
            start = perf_counter()
            for index in range(8):
                engine.publish_taxonomy(
                    replace(
                        tax,
                        provider=replace(
                            tax.provider, taxonomy_version="profile-" + str(index)
                        ),
                    )
                )
            many = tuple(
                snapshot(tax, sample, at=at, soft=(0.3, 0.7)) for at in range(1000, 2000)
            )
            for s in many:
                engine.publish_snapshot(s)
            timings["eight_taxonomies_1000_snapshot_persistence_seconds"] = (
                perf_counter() - start
            )
            start = perf_counter()
            histories = tuple(
                engine.publish_snapshot(
                    snapshot(tax, sample, at=at, state="A" if at < 58 else "B")
                )
                for at in range(50, 61)
            )
            observed = engine.observe(hard.spec, sample.fingerprint, histories)
            timings["matching_sample_and_ten_transition_publication_seconds"] = (
                perf_counter() - start
            )
            assert len(observed.transition_ids) == 10
            start = perf_counter()
            for f in (hard, soft, target_mean):
                engine.fit(f.spec, f.training_ids, 40, 40, 40)
                matrix = repo.get(DesignMatrix, f.model.matrix_id)
                baseline = repo.get(FittedModelArtifact, f.spec.base_model_id)
                rows = {r.sample_id: r for r in matrix.rows}
                os = tuple(repo.get(RegimeConditionedSample, i) for i in f.training_ids)
                for index, state in enumerate(f.model.state_fits):
                    pairs = [
                        (
                            o.membership.weights[index],
                            rows[o.sample_id].response
                            - baseline.intercept
                            - sum(
                                x * c
                                for x, c in zip(
                                    rows[o.sample_id].values, baseline.coefficients, strict=True
                                )
                            ),
                        )
                        for o in os
                        if o.membership and o.membership.weights[index] > 0
                    ]
                    expected = sum(w * y for w, y in pairs) / sum(w for w, _ in pairs)
                    if f is target_mean:
                        expected += baseline.intercept
                    errors[
                        ("target_mean" if f is target_mean else "soft" if f is soft else "hard")
                        + "_state_"
                        + state.state_id
                    ] = abs(expected - (state.value or 0.0))
            timings["three_state_fit_replays_seconds"] = perf_counter() - start
            start = perf_counter()
            for f in (hard, soft):
                for identity in f.forecast_ids:
                    forecast = repo.get(RegimeConditionedForecast, identity)
                    engine.forecast(
                        f.model.fingerprint,
                        forecast.observation_id,
                        forecast.base_forecast_id,
                        60,
                        forecast.base_probability_id,
                    )
                    if forecast.membership:
                        expected = sum(
                            w * (s.value or 0.0)
                            for w, s in zip(
                                forecast.membership.weights, f.model.state_fits, strict=True
                            )
                        )
                        errors["shift:" + identity] = abs(expected - forecast.shift)
            timings["eight_point_probability_applications_seconds"] = perf_counter() - start
            start = perf_counter()
            a = engine.evaluate(hard.forecast_ids, 100, 100)
            soft_eval = engine.evaluate(soft.forecast_ids, 100, 100)
            b = engine.evaluate(hard.test_ids, 100, 100, "profile-regime-TEST")
            timings["three_matched_state_transition_evaluations_seconds"] = (
                perf_counter() - start
            )
            # Exact same truth set in both sides; independent paired MSE change.
            oracle_delta = statistics.mean(
                (p.conditioned - p.truth) ** 2 - (p.base - p.truth) ** 2 for p in a.pairs
            )
            errors["matched_mse_delta"] = abs(
                next(m.value or 0.0 for m in a.deltas if m.name.value == "mse") - oracle_delta
            )
            start = perf_counter()
            rank = engine.rank(hard.upstream.spec, hard.forecast_ids, hard.upstream.group_refs)
            ranked = engine.evaluate_rank(rank.fingerprint, 100, 100)
            cs = repo.get(CrossSectionEvaluation, ranked.cross_section_evaluation_id)
            errors["pearson_IC"] = abs(
                (cs.pearson.value or 0.0)
                - statistics.correlation(
                    [p.conditioned for p in a.pairs], [p.truth for p in a.pairs]
                )
            )
            timings["ranking_matched_IC_seconds"] = perf_counter() - start
            start = perf_counter()
            drift = engine.drift(a.fingerprint, b.fingerprint, 100)

            def state_probability(evaluation: RegimeConditionedEvaluation, state: str) -> float:
                vectors = [
                    repo.get(RegimeConditionedForecast, pair.forecast_id).membership
                    for pair in evaluation.pairs
                ]
                known = [v for v in vectors if v is not None]
                return statistics.mean(v.weights[v.states.index(state)] for v in known)

            errors["drift_probability"] = max(
                abs(delta - (state_probability(b, state) - state_probability(a, state)))
                for state, delta in drift.state_probability_deltas
            )
            timings["drift_without_refit_seconds"] = perf_counter() - start
            t = transition_for(
                snapshot(tax, sample, at=58, soft=(0.8, 0.2)),
                snapshot(tax, sample, at=59, soft=(0.3, 0.7)),
            )
            errors["probability_mass_change"] = abs(t.probability_mass_change - 0.5)
            errors["membership_sum"] = abs(sum(t.current.weights) - 1.0)
            start = perf_counter()
            # Larger synthetic arithmetic workload is separate from causal admitted samples.
            weights = tuple((i % 17 + 1) / 18 for i in range(50_000))
            residuals = tuple((i % 29 - 14) / 100 for i in range(50_000))
            weighted_mean = fsum(w * y for w, y in zip(weights, residuals, strict=True)) / fsum(
                weights
            )
            oracle = statistics.mean(
                w * y for w, y in zip(weights, residuals, strict=True)
            ) / statistics.mean(weights)
            errors["50000_weighted_residual_kernel"] = abs(weighted_mean - oracle)
            support = effective_support(weights)
            timings["50000_weighted_residual_kernel_seconds"] = perf_counter() - start
            start = perf_counter()
            audit = engine.audit_lineage(ranked.fingerprint)
            count = repo.audit()
            timings["bounded_lineage_full_audit_seconds"] = perf_counter() - start
            old = canonical_json(a)
            assert soft_eval.soft_diagnostics
        storage = path.stat().st_size
        start = perf_counter()
        with RegimeRepository(path) as repo:
            assert canonical_json(repo.get_any(a.fingerprint)) == old
            repo.audit()
        timings["restart_full_audit_seconds"] = perf_counter() - start
    assert max(errors.values()) < 1e-12
    output = {
        "engine": "0.12.0",
        "store": "1.11",
        "sqlite_user_version": 12,
        "workload": {
            "additional_taxonomies": 8,
            "additional_snapshots": 1000,
            "causal_TRAIN_samples_per_model": len(hard.training_ids),
            "state_models": 3,
            "causal_history_transitions": 10,
            "deployment_forecasts": 8,
            "bulk_weighted_rows": 50_000,
        },
        "timings": timings,
        "oracle_absolute_errors": errors,
        "maximum_oracle_absolute_error": max(errors.values()),
        "weighted_kernel_effective_support": support,
        "artifact_count": count,
        "audit_nodes": len(audit.evidence_ids),
        "storage_bytes": storage,
        "interpretation": (
            "Synthetic bounded offline causal workflow and separate bulk arithmetic kernel; "
            "no production SLA or profitability claim."
        ),
    }
    encoded = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(encoded)
    print(encoded, end="")


if __name__ == "__main__":
    main()
