"""Offline causal workflow plus separately labelled bounded arithmetic work; no SLA."""

import json
import socket
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import TypeVar

from afre.nonlinear import (
    FittedTransformArtifact,
    InteractionDefinition,
    InteractionTransform,
    NonlinearBounds,
    NonlinearEngine,
    NonlinearForecast,
    NonlinearRepository,
    TreeParameters,
)
from afre.nonlinear.transforms import transform_value
from afre.nonlinear.trees import fit_tree, tree_prediction
from afre.serialization import canonical_json
from afre.statistical_models.linear_algebra import householder_qr
from examples.nonlinear_demo import build_fixture

T = TypeVar("T")


def deny(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in nonlinear profile")


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

    with TemporaryDirectory(prefix="afre-nonlinear-profile-") as directory:
        path = Path(directory) / "research.sqlite"
        with NonlinearRepository(path) as repo:
            fixture = timed("causal_fixture_and_three_families", lambda: build_fixture(repo))
            engine = NonlinearEngine(repo)
            spec = fixture.specs[0]
            state = repo.get(FittedTransformArtifact, fixture.models[0].transform_ids[0])
            definition = repo.get(InteractionDefinition, state.definition_id)
            timed(
                "TRAIN_fitted_transform",
                lambda: engine.fit_transform(spec, definition, fixture.train_ids, 40, 40, 40),
            )
            matrix = timed(
                "TRAIN_matrix",
                lambda: engine.matrix(spec, fixture.train_ids, (state.fingerprint,), 40),
            )
            timed(
                "linear_fit_and_validation",
                lambda: engine.fit(spec, matrix.fingerprint, 40, 40, 40),
            )
            tree = fixture.models[2]
            timed(
                "tree_fit_and_validation",
                lambda: engine.fit(fixture.specs[2], tree.matrix_id, 40, 40, 40),
            )
            f = repo.get(NonlinearForecast, fixture.forecast_ids[0][0])
            timed(
                "prediction_and_publication",
                lambda: engine.predict(
                    f.model_id,
                    f.input_id,
                    60,
                    f.probability.base_forecast_id if f.probability else None,
                ),
            )
            evaluation = timed(
                "matched_evaluation", lambda: engine.evaluate(fixture.forecast_ids[0], 100, 100)
            )
            cs = fixture.upstream.upstream.upstream
            timed(
                "same_origin_ranking",
                lambda: engine.rank(cs.spec, fixture.forecast_ids[0], cs.group_refs),
            )
            alternate = replace(spec, seed=2)
            piece = next(
                d
                for d in alternate.interaction_set.definitions
                if d.interaction_id == "piecewise"
            )
            alt_state = engine.fit_transform(alternate, piece, fixture.train_ids, 40, 40, 40)
            alt_matrix = engine.matrix(
                alternate, fixture.train_ids, (alt_state.fingerprint,), 40
            )
            alt_model = engine.fit(alternate, alt_matrix.fingerprint, 40, 40, 40)
            timed(
                "compatible_model_stability",
                lambda: engine.stability(
                    (fixture.models[0].fingerprint, alt_model.fingerprint), 100
                ),
            )
            audit = timed("bounded_lineage", lambda: engine.audit_lineage(f.fingerprint))
            timed("repository_audit", repo.audit)
            identities = tuple(
                r[0]
                for r in repo._connection.execute(
                    "SELECT fingerprint FROM nl_artifacts ORDER BY fingerprint"
                )
            )
            before = timed(
                "serialization",
                lambda: tuple(canonical_json(repo.get_any(i)) for i in identities),
            )
            timed("idempotent_persistence", lambda: engine._publish((f, evaluation)))
            size = path.stat().st_size + sum(
                p.stat().st_size for p in path.parent.glob("*.sqlite-wal")
            )
            product = next(
                d
                for d in spec.interaction_set.definitions
                if d.transform is InteractionTransform.PRODUCT
            )
            timed(
                "40000_explicit_product_applications",
                lambda: tuple(transform_value(product, (2.0, 3.0)) for _ in range(40_000)),
            )

        def restart() -> bool:
            with NonlinearRepository(path) as reopened:
                return tuple(canonical_json(reopened.get_any(i)) for i in identities) == before

        assert timed("restart_replay", restart)
    # Independent arithmetic matrices are not AFRE-4 samples or historical TRAIN evidence.
    x = tuple((1.0, float(i) / 100, float(i % 7)) for i in range(2000))
    y = tuple(1 + 2 * r[1] - 3 * r[2] for r in x)
    qr = timed("arithmetic_2000_row_QR", lambda: householder_qr(x, y, 1e-12, 1e12))
    ids = tuple("afre.r_sample:1.0:" + f"{i + 1:064x}" for i in range(len(x)))
    nodes = timed(
        "arithmetic_2000_row_shallow_tree",
        lambda: fit_tree(
            ("time", "state"),
            tuple(r[1:] for r in x),
            y,
            ids,
            TreeParameters(2, 8, 16),
            NonlinearBounds(),
        ),
    )
    timed(
        "arithmetic_tree_predictions",
        lambda: tuple(tree_prediction(nodes, ("time", "state"), r[1:]) for r in x),
    )
    error = max(abs(a - b) for a, b in zip(qr.coefficients, (1.0, 2.0, -3.0), strict=True))
    assert error < 1e-9
    return {
        "engine_version": "0.14.0",
        "store": "1.13",
        "sqlite_user_version": 14,
        "runtime_dependencies": [],
        "offline": True,
        "causal_TRAIN_rows": len(fixture.train_ids),
        "arithmetic_rows_not_causal_TRAIN": 2000,
        "transform_applications": 40_000,
        "interaction_definitions": len(spec.interaction_set.definitions),
        "tree_nodes": len(nodes),
        "nonlinear_artifacts": len(identities),
        "lineage_nodes": len(audit.node_ids),
        "storage_including_WAL_bytes": size,
        "maximum_QR_coefficient_error": error,
        "restart_bytes_identical": True,
        "seconds": timings,
        "production_SLA": False,
    }


if __name__ == "__main__":
    print(json.dumps(profile(), sort_keys=True, indent=2))
