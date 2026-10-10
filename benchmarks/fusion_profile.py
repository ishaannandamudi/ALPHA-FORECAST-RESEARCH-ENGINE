"""Measured bounded offline fusion operations; distinct rows are counted honestly."""

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.fusion import (
    FusedForecast,
    FusionEngine,
    FusionFamily,
    FusionIntercept,
    FusionObservation,
    FusionRepository,
    FusionWeights,
)
from afre.serialization import canonical_json
from examples.fusion_fixture import apply_partition, build_fixture
from examples.fusion_oracles import diagnostic_errors
from examples.fusion_probabilities import probability_fixture


def profile() -> dict[str, object]:
    times: dict[str, float] = {}
    with TemporaryDirectory(prefix="afre-fusion-profile-") as directory:
        path = Path(directory) / "research.sqlite"
        with FusionRepository(path) as repo:
            start = perf_counter()
            f = build_fixture(repo)
            times["fixture_seconds"] = perf_counter() - start
            e = FusionEngine(repo)
            start = perf_counter()
            for i in f.observations(f.validation[0]):
                repo.resolve(FusionObservation, i)
            times["source_resolution_seconds"] = perf_counter() - start
            start = perf_counter()
            fixed = e.fit(f.spec, 0, 0, 0)
            times["fixed_fusion_seconds"] = perf_counter() - start
            spec = replace(
                f.spec,
                name="profile-learned",
                family=FusionFamily.LEARNED_LINEAR_POINT,
                weights=(),
                weight_policy=FusionWeights.UNCONSTRAINED_QR,
                intercept_policy=FusionIntercept.WITH_INTERCEPT,
            )
            start = perf_counter()
            learned = e.fit(spec, 40, 40, 40, tuple((i, f.observations(i)) for i in f.train))
            times["learned_fitting_seconds"] = perf_counter() - start
            start = perf_counter()
            ids = apply_partition(repo, f, learned.fingerprint, (*f.validation, *f.test))
            fixed_ids = apply_partition(repo, f, fixed.fingerprint, (*f.validation, *f.test))
            times["application_seconds"] = perf_counter() - start
            start = perf_counter()
            probability_spec, probability_ids = probability_fixture(repo, f)
            probability_artifact = e.fit(probability_spec, 0, 0, 0)
            probability = e.apply(
                probability_artifact.fingerprint, f.validation[0], probability_ids, 40
            )
            times["probabilistic_mixture_seconds"] = perf_counter() - start
            start = perf_counter()
            diversity = e.diversity(
                f.spec.source_ids,
                tuple(i for s in f.validation for i in f.observations(s)),
                100,
            )
            times["diversity_seconds"] = perf_counter() - start
            start = perf_counter()
            validation_ids = tuple(
                i for i in ids if repo.get(FusedForecast, i).sample_id in f.validation
            )
            pool = e.trial_pool(((spec.fingerprint, validation_ids),))
            comparison = e.evaluate(validation_ids, pool.fingerprint, 100, 100)
            times["evaluation_seconds"] = perf_counter() - start
            errors = diagnostic_errors(repo, diversity, comparison)
            start = perf_counter()
            audit = e.audit(comparison.fingerprint)
            times["audit_seconds"] = perf_counter() - start
            start = perf_counter()
            with sqlite3.connect(Path(directory) / "snapshot.sqlite") as target:
                repo._connection.backup(target)
            times["persistence_backup_seconds"] = perf_counter() - start
            pages = repo._connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = repo._connection.execute("PRAGMA page_size").fetchone()[0]
            stored = repo._connection.execute("SELECT count(*) FROM fus_artifacts").fetchone()[
                0
            ]
            frozen = canonical_json(probability)
        start = perf_counter()
        with FusionRepository(path) as reopened:
            assert (
                canonical_json(reopened.resolve(FusedForecast, probability.fingerprint))
                == frozen
            )
        times["restart_seconds"] = perf_counter() - start
    return {
        "production_SLA": False,
        "runtime_dependencies": 0,
        "diagnostic_numerical_errors": errors,
        "max_diagnostic_numerical_error": max(errors.values()),
        "source_columns": 2,
        "TRAIN_rows": len(learned.rows),
        "unique_application_rows": len(set((*ids, *fixed_ids))),
        "unique_security_origins": len(f.validation) + len(f.test),
        "probability_components": 2,
        "diversity_cells": len(diversity.pairs),
        "comparison_pairs": len(comparison.pairs),
        "audit_nodes": len(audit.node_ids),
        "audit_bytes": audit.serialized_bytes,
        "stored_fusion_artifacts": stored,
        "SQLite_page_bytes": pages * page_size,
        **times,
        "limitations": (
            "Small offline profile; operation times include semantic replay and publication; "
            "persistence measures actual SQLite backup; no repeated idempotent request "
            "counted as a new causal row."
        ),
    }


def main() -> None:
    print(json.dumps(profile(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
