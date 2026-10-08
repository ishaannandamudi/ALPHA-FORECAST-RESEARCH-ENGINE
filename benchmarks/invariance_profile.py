"""Bounded offline native workflow and separately reported arithmetic load; no SLA."""

import json
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TypeVar

from afre.invariance import (
    EnvironmentMembership,
    InvarianceEngine,
    InvarianceRepository,
    StabilityMetricName,
)
from afre.invariance.distributions import empirical_ks
from afre.orthogonalization import SignalObservation
from afre.research_datasets.schema import Partition
from afre.serialization import canonical_json
from examples.invariance_fixture import build_fixture

T = TypeVar("T")


def timed(fn: Callable[[], T]) -> tuple[T, float]:
    start = perf_counter()
    value = fn()
    return value, perf_counter() - start


def profile() -> dict[str, object]:
    with TemporaryDirectory(prefix="afre17-profile-") as folder:
        path = Path(folder) / "profile.sqlite"
        with InvarianceRepository(path) as repo:
            f, fixture_s = timed(lambda: build_fixture(repo))
            e = InvarianceEngine(repo)
            _, construction_s = timed(
                lambda: tuple(
                    e.bind(
                        repo.get(EnvironmentMembership, i).environment_id,
                        repo.get(EnvironmentMembership, i).sample_id,
                        constructed_ns=repo.get(EnvironmentMembership, i).constructed_ns,
                    )
                    for i in f.membership_ids
                )
            )
            ms, aggregation_s = timed(
                lambda: e.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
            )
            _, membership_s = timed(
                lambda: tuple(
                    e.metadata(i, repo.get(EnvironmentMembership, i).origin)
                    for i in f.membership_ids
                )
            )
            ref = f.upstream.spec.candidate.fingerprint
            obs = tuple(
                i
                for row in f.upstream.partition(Partition.VALIDATION)
                for i in row.observation_ids
                if repo.get(SignalObservation, i).reference_id == ref
            )
            shift, shift_s = timed(
                lambda: e.shift(
                    f.spec.fingerprint,
                    ref,
                    (
                        f.environment_set.definitions[0].fingerprint,
                        f.environment_set.definitions[1].fingerprint,
                    ),
                    f.membership_ids,
                    obs,
                    100,
                    100,
                )
            )
            mae = tuple(m for m in ms if m.name is StabilityMetricName.MAE)
            a = next(m for m in mae if m.environment_id == f.spec.baseline_environment_id)
            b = next(m for m in mae if m.environment_id != f.spec.baseline_environment_id)
            c, comparison_s = timed(lambda: e.compare(a.fingerprint, b.fingerprint, 100))
            _, degradation_s = timed(lambda: e.degradation(c.fingerprint))
            model = f.upstream.upstream.covariances[0].model_id
            _, coefficient_s = timed(
                lambda: e.models(
                    f.spec.fingerprint,
                    tuple((d.fingerprint, model) for d in f.environment_set.definitions),
                    100,
                    100,
                    True,
                )
            )
            audit, audit_s = timed(lambda: e.audit(c.fingerprint))
            _, persistence_s = timed(lambda: e._publish(ms))
            identities = tuple(
                row[0]
                for row in repo._connection.execute(
                    "SELECT fingerprint FROM inv_artifacts ORDER BY fingerprint"
                )
            )
            before = tuple(canonical_json(repo.get_any(i)) for i in identities)
            payload = repo._connection.execute(
                "SELECT sum(length(payload)) FROM inv_artifacts"
            ).fetchone()[0]
        start = perf_counter()
        with InvarianceRepository(path) as repo:
            assert before == tuple(canonical_json(repo.get_any(i)) for i in identities)
        restart_s = perf_counter() - start
        aa, bb = tuple(float(i) for i in range(2000)), tuple(float(i) + 3 for i in range(2000))
        _, kernel_s = timed(lambda: tuple(empirical_ks(aa, bb) for _ in range(32)))
        oracle_ks = max(
            abs(
                sum(v <= x for _, v in shift.left.values if v is not None)
                / len(shift.left.values)
                - sum(v <= x for _, v in shift.right.values if v is not None)
                / len(shift.right.values)
            )
            for x in {v for _, v in (*shift.left.values, *shift.right.values) if v is not None}
        )
        return {
            "engine": "0.18.0",
            "store": "1.17",
            "schema": "1.0",
            "native_environments": 2,
            "native_samples": 12,
            "native_memberships": 24,
            "native_metrics": len(ms),
            "audit_nodes": len(audit.node_ids),
            "artifacts": len(identities),
            "canonical_payload_bytes": payload,
            "sqlite_bytes": path.stat().st_size,
            "seconds": {
                "upstream_fixture_and_declaration": fixture_s,
                "membership_construction_and_idempotent_publication": construction_s,
                "membership_replay": membership_s,
                "environment_aggregation": aggregation_s,
                "feature_shift": shift_s,
                "comparison": comparison_s,
                "degradation": degradation_s,
                "coefficients": coefficient_s,
                "audit": audit_s,
                "idempotent_persistence": persistence_s,
                "restart": restart_s,
                "separate_32_by_2000_KS_kernel": kernel_s,
            },
            "maximum_numerical_error": {
                "KS": abs((shift.ks_distance or 0) - oracle_ks),
                "degradation": abs((c.delta or 0) - ((b.value or 0) - (a.value or 0))),
            },
            "limits": "Offline synthetic measurement; arithmetic workload is separate "
            "from the native workflow; no production SLA.",
        }


def main() -> None:
    print(json.dumps(profile(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
