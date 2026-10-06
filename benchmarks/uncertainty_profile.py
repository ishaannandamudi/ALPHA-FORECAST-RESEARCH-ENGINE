"""Bounded offline workflow; repeated arithmetic is explicitly separated from new data."""

import json
import socket
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TypeVar

from afre.serialization import canonical_json
from afre.statistical_models.artifacts import DesignMatrix
from afre.uncertainty import (
    ForecastUncertaintyDecomposition,
    ParameterUncertaintySpec,
    UncertaintyEngine,
    UncertaintyEvaluationSpec,
    UncertaintyRepository,
    UncertaintySpec,
)
from afre.uncertainty.components import component_for
from afre.uncertainty.covariance import inverse_crossproduct, quadratic_variance
from afre.uncertainty.decomposition import decomposition_for
from afre.uncertainty.intervals import interval_for
from afre.uncertainty.moments import mixture_terms
from afre.uncertainty.sources import source_for
from examples.uncertainty_fixture import build_fixture
from examples.uncertainty_oracles import ols_covariance, prediction_variance

T = TypeVar("T")


def denied(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in uncertainty profile")


def profile() -> dict[str, object]:
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

    def timed(name: str, callback: Callable[[], T]) -> T:
        start = perf_counter()
        result = callback()
        timings[name] = perf_counter() - start
        return result

    with TemporaryDirectory(prefix="afre-uncertainty-profile-") as folder:
        path = Path(folder) / "research.sqlite"
        with UncertaintyRepository(path) as repo:
            fixture = timed(
                "causal_fixture_44_validation_4_test_decompositions",
                lambda: build_fixture(repo),
            )
            engine = UncertaintyEngine(repo)
            result = repo.get(ForecastUncertaintyDecomposition, fixture.results("gaussian")[0])
            spec = repo.get(UncertaintySpec, result.spec_id)
            with repo.read_snapshot(), repo.validation_cache(), repo.feature_only():
                source = source_for(repo, result.forecast_id)
                interval = timed("interval_extraction", lambda: interval_for(spec, source, 60))
                timed(
                    "component_construction",
                    lambda: tuple(
                        component_for(repo, spec, r, source, interval, 60)
                        for r in spec.requests
                    ),
                )
                timed(
                    "decomposition_replay_validation", lambda: decomposition_for(repo, spec, 60)
                )
            timed(
                "TRAIN_covariance_fit",
                lambda: engine.fit_covariance(
                    repo.get(ParameterUncertaintySpec, fixture.covariances[0].spec_id), 40
                ),
            )
            matrix = repo.get(DesignMatrix, fixture.covariances[0].matrix_id)
            design = tuple((1.0, *r.values) for r in matrix.rows)
            oracle, sigma = ols_covariance(design, tuple(r.response for r in matrix.rows))
            inverse, _ = timed(
                "covariance_QR_200_arithmetic_repetitions",
                lambda: tuple(inverse_crossproduct(design, 1e-10, 1e10) for _ in range(200))[
                    -1
                ],
            )
            errors = [
                abs(a - sigma * b)
                for r, s in zip(oracle, inverse, strict=True)
                for a, b in zip(r, s, strict=True)
            ]
            errors.append(
                abs(
                    prediction_variance(design[-1], oracle)
                    - quadratic_variance(design[-1], oracle)
                )
            )
            from afre.mixture import MixtureForecast

            law = repo.get(
                MixtureForecast,
                repo.get(
                    ForecastUncertaintyDecomposition, fixture.results("mixture")[0]
                ).forecast_id,
            ).distribution
            assert law is not None
            timed(
                "mixture_moments_1000_arithmetic_repetitions",
                lambda: tuple(mixture_terms(law) for _ in range(1000)),
            )
            policy = UncertaintyEvaluationSpec(bucket_count=2)
            evaluations = timed(
                "eleven_source_evaluations_44_samples",
                lambda: tuple(
                    engine.evaluate(ids, policy, 100, 100) for _, ids in fixture.decompositions
                ),
            )
            validation = engine.evaluate(fixture.results("gaussian"), policy, 100, 100)
            test = engine.evaluate(fixture.test_ids, policy, 100, 100, "profile-test")
            timed(
                "drift_two_known_windows",
                lambda: engine.drift((validation.fingerprint, test.fingerprint), 100),
            )
            audit = timed(
                "bounded_unified_audit", lambda: engine.audit_lineage(validation.fingerprint)
            )
            ids = tuple(
                r[0]
                for r in repo._connection.execute(
                    "SELECT fingerprint FROM unc_artifacts ORDER BY fingerprint"
                )
            )
            values = tuple(repo.get_any(i) for i in ids)
            payloads = timed(
                "canonical_serialization", lambda: tuple(canonical_json(v) for v in values)
            )

            def persist() -> None:
                with repo.transaction(), repo.validation_cache():
                    for v in values:
                        repo.put(v)

            timed("idempotent_persistence", persist)
            total_storage = sum(p.stat().st_size for p in Path(folder).glob("research.sqlite*"))

        def restart() -> None:
            with UncertaintyRepository(path) as reopened:
                assert tuple(canonical_json(reopened.get_any(i)) for i in ids) == payloads

        timed("restart_and_byte_replay", restart)
        return {
            "engine_version": "0.16.0",
            "uncertainty_schema": "1.0",
            "store": "1.15",
            "user_version": 16,
            "offline": True,
            "timings_seconds": timings,
            "counts": {
                "validation_decompositions": sum(len(v) for _, v in fixture.decompositions),
                "test_decompositions": len(fixture.test_ids),
                "source_families": len(fixture.sources),
                "covariances": len(fixture.covariances),
                "TRAIN_rows_each": len(matrix.rows),
                "covariance_dimensions": len(design[0]),
                "evaluation_pairs": sum(len(e.pairs) for e in evaluations),
                "audit_nodes": len(audit.node_ids),
                "uncertainty_artifacts": len(ids),
            },
            "max_absolute_covariance_prediction_oracle_error": max(errors),
            "canonical_uncertainty_bytes": sum(len(p.encode()) for p in payloads),
            "sqlite_closed_bytes": path.stat().st_size,
            "sqlite_open_including_WAL_bytes": total_storage,
            "scope": (
                "neutral bounded causal fixtures; arithmetic repetitions are not "
                "independent samples; no production SLA"
            ),
        }


if __name__ == "__main__":
    print(json.dumps(profile(), indent=2, sort_keys=True))
