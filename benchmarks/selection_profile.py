"""Measured small offline exhaustive grid, without SLA or extrapolation."""

import json
from dataclasses import replace
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.selection import (
    DiscreteDimension,
    SelectionEngine,
    SelectionRepository,
    enumerate_candidates,
)
from afre.selection.results import SelectionResult
from afre.serialization import canonical_json
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.schema import ModelFamily
from examples.selection_fixture import small_fixture
from examples.selection_oracles import numerical_errors


def profile() -> dict[str, object]:
    with TemporaryDirectory(prefix="afre-selection-profile-") as directory:
        path = Path(directory) / "research.sqlite"
        with SelectionRepository(path) as repo:
            start = perf_counter()
            fixture = small_fixture(repo)
            fixture_seconds = perf_counter() - start
            reference = next(
                r
                for r in fixture.space.recipes
                if isinstance(r.native_spec, BaselineModelSpec)
                and r.native_spec.family is ModelFamily.REFERENCE_VALUE
            )
            spec = reference.native_spec
            assert isinstance(spec, BaselineModelSpec)
            recipes = tuple(
                replace(
                    reference,
                    native_spec=replace(spec, random_seed=seed, reference_value=value),
                    choices=(("reference", str(value)), ("seed", str(seed))),
                )
                for seed, value in product((0, 1, 2, 3), (0.0, 0.03))
            )
            space = replace(
                fixture.space,
                search_key="bounded-profile-grid",
                dimensions=(
                    DiscreteDimension("seed", ("0", "1", "2", "3")),
                    DiscreteDimension("reference", ("0.0", "0.03")),
                ),
                recipes=recipes,
            )
            start = perf_counter()
            candidates = enumerate_candidates(space)
            enumeration_seconds = perf_counter() - start
            assert len(candidates) == 8
            engine = SelectionEngine(repo)
            result, registry = engine.select(space, 100, 100)
            start = perf_counter()
            audit = engine.audit(result.fingerprint)
            audit_seconds = perf_counter() - start
            frozen = canonical_json(result)
            pages = repo._connection.execute("PRAGMA page_count").fetchone()[0]
            page_size = repo._connection.execute("PRAGMA page_size").fetchone()[0]
            storage = pages * page_size
            timings = dict(engine.last_timings)
        start = perf_counter()
        with SelectionRepository(path) as reopened:
            replay = reopened.resolve(SelectionResult, result.fingerprint)
            assert canonical_json(replay) == frozen
        restart_seconds = perf_counter() - start
        return {
            "fixture": "eight-reference-candidates-four-seeds-two-values-one-fold",
            "production_SLA": False,
            "candidate_count": len(candidates),
            "dimensions": 2,
            "TRAIN_rows_reserved": result.usage.train_rows_reserved,
            "VALIDATION_pairs": result.usage.validation_pairs,
            "fit_operations_reserved": result.usage.fit_operations_reserved,
            "registry_candidates": len(registry.entries),
            "audit_nodes": len(audit.node_ids),
            "audit_bytes": audit.serialized_bytes,
            "SQLite_page_bytes": storage,
            "fixture_seconds": fixture_seconds,
            "enumeration_seconds": enumeration_seconds,
            **timings,
            "audit_seconds": audit_seconds,
            "restart_seconds": restart_seconds,
            "independent_oracle_absolute_errors": numerical_errors(),
            "limitations": (
                "single small synthetic offline grid; timings include native semantic "
                "validation; no wall-clock stopping; no scale extrapolation"
            ),
        }


def main() -> None:
    print(json.dumps(profile(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
