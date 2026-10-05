"""Bounded offline causal workflow plus separately labelled larger arithmetic kernels."""

import json
import socket
import sys
from math import erf, fsum, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.mixture import (
    ExpertForecastBinding,
    MixtureEngine,
    MixtureForecast,
    MixtureRepository,
)
from afre.mixture.learned import solve_simplex
from afre.mixture.probabilistic import (
    mixture_cdf,
    mixture_expectation,
    mixture_scores,
    mixture_threshold,
    mixture_variance,
)
from afre.probabilistic.definitions import ThresholdRequest
from afre.probabilistic.distributions import conditional_variance, expected_value
from afre.probabilistic.schema import ThresholdComparison
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from examples.mixture_demo import build_fixture, external_binding


def denied(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in mixture profile")


def main() -> None:
    for name in (
        "socket",
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
        "socketpair",
    ):
        setattr(socket, name, denied)
    timings: dict[str, float] = {}
    errors: dict[str, float] = {}
    with TemporaryDirectory() as folder:
        path = Path(folder) / "profile.sqlite"
        start = perf_counter()
        with MixtureRepository(path) as repo:
            fixture = build_fixture(repo)
            engine = MixtureEngine(repo)
            timings["causal_fixture_seconds"] = perf_counter() - start
            first = repo.get(MixtureForecast, fixture.forecast_ids[0])
            sample = repo.get(ResearchSample, first.request.sample_id)
            start = perf_counter()
            for _ in range(1000):
                for _, identity in first.request.expert_inputs:
                    if identity:
                        repo.get(ExpertForecastBinding, identity)
            timings["6000_exact_expert_binding_reads_seconds"] = perf_counter() - start
            start = perf_counter()
            model = engine.fit(fixture.learned_spec, fixture.training_ids, 40, 40, 40)
            timings["12_causal_train_rows_fit_replay_seconds"] = perf_counter() - start
            assert model == fixture.learned
            start = perf_counter()
            for identity in fixture.forecast_ids:
                value = repo.get(MixtureForecast, identity)
                assert engine.forecast(value.request) == value
            timings["four_fixed_mixture_replay_seconds"] = perf_counter() - start
            external = fixture.learned_spec.expert_set.experts[0]
            start = perf_counter()
            for index in range(1000):
                external_binding(
                    repo, external, sample, 0.001, revision="profile-" + str(index)
                )
            timings["1000_external_revision_and_binding_publications_seconds"] = (
                perf_counter() - start
            )
            start = perf_counter()
            p = repo.get(MixtureForecast, fixture.probability_ids[0])
            assert p.distribution is not None
            request = ThresholdRequest(0.0, ThresholdComparison.GT)
            for _ in range(1000):
                mixture_scores(p.distribution, 0.02, (request,))
                mixture_variance(p.distribution)
            timings["1000_finite_probability_calculations_seconds"] = perf_counter() - start
            component_means = tuple(
                expected_value(c.distribution) for c in p.distribution.components
            )
            mean = fsum(
                c.weight * (m or 0.0)
                for c, m in zip(p.distribution.components, component_means, strict=True)
            )
            var = (
                fsum(
                    c.weight * ((conditional_variance(c.distribution) or 0.0) + (m or 0.0) ** 2)
                    for c, m in zip(p.distribution.components, component_means, strict=True)
                )
                - mean**2
            )
            errors["mixture_expectation"] = abs(mixture_expectation(p.distribution) - mean)
            errors["mixture_variance"] = abs(mixture_variance(p.distribution) - var)
            errors["threshold_cdf_complement"] = abs(
                mixture_threshold(p.distribution, request)
                + mixture_cdf(p.distribution, 0.0)
                - 1.0
            )
            start = perf_counter()
            evaluation = engine.evaluate(fixture.forecast_ids, 100, 100)
            timings["matched_evaluation_seconds"] = perf_counter() - start
            start = perf_counter()
            diagnostic = engine.diagnostics(evaluation.fingerprint)
            test = engine.evaluate(fixture.test_ids, 100, 100, "mixture-profile-TEST")
            engine.drift(
                diagnostic.fingerprint, engine.diagnostics(test.fingerprint).fingerprint, 100
            )
            timings["diagnostics_and_drift_seconds"] = perf_counter() - start
            errors["effective_expert_count"] = abs(diagnostic.mean_effective_expert_count - 6.0)
            start = perf_counter()
            upstream = fixture.upstream.upstream
            rank = engine.rank(upstream.spec, fixture.forecast_ids, upstream.group_refs)
            rank_eval = engine.evaluate_rank(rank.fingerprint, 100, 100)
            timings["ranking_and_ic_seconds"] = perf_counter() - start
            start = perf_counter()
            audit = engine.audit_lineage(rank_eval.fingerprint)
            timings["unified_lineage_seconds"] = perf_counter() - start
            payload = canonical_json(first)
            stored = repo._connection.execute("SELECT count(*) FROM mix_artifacts").fetchone()[
                0
            ]
            repo._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            storage = path.stat().st_size
        start = perf_counter()
        with MixtureRepository(path) as reader:
            assert canonical_json(reader.get(MixtureForecast, first.fingerprint)) == payload
            timings["restart_and_exact_lookup_seconds"] = perf_counter() - start
            start = perf_counter()
            reader.audit()
            timings["deep_repository_audit_seconds"] = perf_counter() - start
    start = perf_counter()
    matrix = tuple((float(i % 11) / 1000, 1.0 + float(i % 11) / 1000) for i in range(10000))
    responses = tuple(0.25 + row[0] for row in matrix)
    weights, iterations, residual, _ = solve_simplex(matrix, responses)
    timings["10000_arithmetic_rows_simplex_kernel_seconds"] = perf_counter() - start
    errors["simplex_known_solution"] = max(
        abs(a - b) for a, b in zip(weights, (0.75, 0.25), strict=True)
    )
    start = perf_counter()
    points = tuple(fsum((0.25 * 1.0, 0.75 * 3.0)) for _ in range(50000))
    timings["50000_weighted_point_arithmetic_seconds"] = perf_counter() - start
    errors["weighted_point"] = max(abs(x - 2.5) for x in points)
    # Independent scalar Gaussian oracle; the causal fixture also covers mixed empirical laws.
    from afre.mixture.artifacts import MixtureComponent, MixtureDistribution
    from afre.probabilistic.artifacts import DistributionParameters
    from afre.probabilistic.schema import DistributionFamily

    ids = fixture.probability.expert_set.expert_ids
    bindings = tuple(c.binding_id for c in p.distribution.components)
    gaussian = MixtureDistribution(
        tuple(
            MixtureComponent(
                identity,
                binding,
                weight,
                DistributionParameters(
                    DistributionFamily.GAUSSIAN_LOCATION_SCALE, location, scale
                ),
            )
            for identity, binding, weight, location, scale in zip(
                ids[:2], bindings[:2], (0.25, 0.75), (-0.5, 1.0), (0.7, 1.3), strict=True
            )
        )
    )
    x = 0.4
    oracle = fsum(
        c.weight * (1 + erf((x - c.distribution.location) / c.distribution.scale / sqrt(2))) / 2
        for c in gaussian.components
    )
    errors["gaussian_cdf"] = abs(mixture_cdf(gaussian, x) - oracle)
    assert max(errors.values()) < 1e-8
    result = {
        "engine": "0.13.0",
        "schema": "1.0",
        "offline": True,
        "runtime_dependencies": [],
        "causal_train_rows": 12,
        "causal_origins": [60, 80],
        "point_experts": 6,
        "probabilistic_experts": 3,
        "external_revisions": 1000,
        "arithmetic_kernel_rows": 10000,
        "kernel_rows_are_not_causal_train_evidence": True,
        "iterations": iterations,
        "convergence_residual": residual,
        "stored_mixture_artifacts": stored,
        "lineage_nodes": len(audit.evidence_ids),
        "storage_bytes": storage,
        "seconds": timings,
        "maximum_absolute_numerical_errors": errors,
        "production_sla": False,
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
