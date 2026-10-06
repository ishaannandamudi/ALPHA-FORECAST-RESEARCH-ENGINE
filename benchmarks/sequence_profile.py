"""Bounded offline causal workflow and separately labelled temporal arithmetic profile."""

import json
import socket
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TypeVar

from afre.sequence import (
    SequenceDataset,
    SequenceEngine,
    SequenceForecast,
    SequenceRepository,
    SequenceSnapshot,
    SequenceTransformArtifact,
)
from afre.sequence.models import temporal_features
from afre.serialization import canonical_json
from examples.sequence_demo import build_fixture
from examples.sequence_oracles import ridge_oracle

T = TypeVar("T")


def deny(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in sequence profile")


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
        setattr(socket, name, deny)
    timings: dict[str, float] = {}

    def timed(name: str, callback: Callable[[], T]) -> T:
        start = perf_counter()
        result = callback()
        timings[name] = perf_counter() - start
        return result

    with TemporaryDirectory(prefix="afre-sequence-profile-") as directory:
        path = Path(directory) / "research.sqlite"
        with SequenceRepository(path) as repo:
            fixture = timed(
                "causal_cross_domain_fixture_and_two_families", lambda: build_fixture(repo)
            )
            engine = SequenceEngine(repo)
            spec, model = fixture.specs[0], fixture.models[0]
            snapshots = timed(
                "window_extraction_alignment_masking_24_snapshots",
                lambda: tuple(
                    engine.snapshot(
                        (s := repo.get(SequenceSnapshot, i)).origin,
                        spec.features,
                        spec.window,
                        s.computed_ns,
                        s.candidate_ids,
                    )
                    for _, i in (*fixture.bindings, *fixture.validation)
                ),
            )
            timed(
                "aligned_feature_column_scan",
                lambda: tuple(
                    tuple(row[j] for s in snapshots for row in s.values)
                    for j in range(len(spec.features))
                ),
            )
            timed("mask_scan", lambda: sum(sum(row) for s in snapshots for row in s.mask))
            state = timed(
                "TRAIN_normalization",
                lambda: engine.fit_transform(spec, fixture.bindings, 40, 40, 40),
            )
            dataset = timed(
                "TRAIN_dataset", lambda: engine.dataset(spec, state.fingerprint, 40)
            )
            timed("decay_QR_fit", lambda: engine.fit(spec, dataset.fingerprint, 40, 40, 40))
            timed(
                "state_space_QR_fit",
                lambda: engine.fit(fixture.specs[1], fixture.models[1].dataset_id, 40, 40, 40),
            )
            f = repo.get(SequenceForecast, fixture.forecasts[0][0])
            timed(
                "prediction",
                lambda: engine.predict(
                    f.model_id,
                    f.sample_id,
                    f.snapshot_id,
                    60,
                    f.probability.base_forecast_id if f.probability else None,
                ),
            )
            timed("evaluation", lambda: engine.evaluate(fixture.forecasts[0], 100, 100))
            cs = fixture.upstream.upstream.upstream.upstream
            timed("ranking", lambda: engine.rank(cs.spec, fixture.forecasts[0], cs.group_refs))
            audit = timed("audit", lambda: engine.audit_lineage(f.fingerprint))
            snap = repo.get(SequenceSnapshot, f.snapshot_id)
            timed(
                "temporal_transform_3200_arithmetic_repetitions",
                lambda: tuple(temporal_features(spec, snap, state)[0] for _ in range(3200)),
            )
            errors: list[float] = []
            for spec, model in zip(fixture.specs, fixture.models, strict=True):
                data = repo.get(SequenceDataset, model.dataset_id)
                fitted = repo.get(SequenceTransformArtifact, model.transform_id)
                # Distinct readout solver; independent temporal fixtures live in tests.
                x = tuple(
                    temporal_features(spec, repo.get(SequenceSnapshot, r.snapshot_id), fitted)[
                        0
                    ]
                    for r in data.rows
                )
                oracle = ridge_oracle(
                    x, tuple(r.response for r in data.rows), spec.ridge_penalty
                )
                errors.extend(
                    abs(a - b)
                    for a, b in zip((model.intercept, *model.coefficients), oracle, strict=True)
                )
            ids = tuple(
                r[0]
                for r in repo._connection.execute(
                    "SELECT fingerprint FROM sq_artifacts ORDER BY fingerprint"
                )
            )
            before = timed(
                "canonical_serialization",
                lambda: tuple(canonical_json(repo.get_any(i)) for i in ids),
            )
            timed(
                "idempotent_persistence",
                lambda: engine.predict(
                    f.model_id,
                    f.sample_id,
                    f.snapshot_id,
                    60,
                    f.probability.base_forecast_id if f.probability else None,
                ),
            )
            payload_bytes = sum(len(v.encode()) for v in before)

        def reopen() -> int:
            with SequenceRepository(path) as reader:
                assert tuple(canonical_json(reader.get_any(i)) for i in ids) == before
                return len(ids)

        timed("restart_and_verified_replay", reopen)
        return {
            "engine": "0.15.0",
            "store": "1.14",
            "schema": "1.0",
            "sqlite_user_version": 15,
            "network": "socket and DNS blocked",
            "runtime_dependencies": [],
            "causal_TRAIN_rows": len(fixture.bindings),
            "features": len(fixture.features),
            "maximum_sequence_length": fixture.specs[0].window.maximum_observations,
            "arithmetic_repetitions": 3200,
            "arithmetic_scope": "Inference repetitions; not additional causal TRAIN samples",
            "sequence_artifacts": len(ids),
            "sequence_payload_bytes": payload_bytes,
            "sqlite_bytes": path.stat().st_size,
            "lineage_nodes": len(audit.node_ids),
            "maximum_readout_oracle_error": max(errors),
            "timings_seconds": timings,
            "limitations": (
                "Synthetic research profile; no production SLA. "
                "Alignment and mask construction measured jointly with extraction; "
                "separate scans reported."
            ),
        }


if __name__ == "__main__":
    print(json.dumps(profile(), sort_keys=True, indent=2))
