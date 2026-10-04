from dataclasses import replace

import pytest

from afre.feature_store import AvailabilityEvidence
from afre.feature_store.schema import AvailabilityMode
from afre.features import DataQuality, MissingState
from afre.ids import InstrumentId
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.target_engine import TargetEngine, TargetSetManifest, TargetVintage
from afre.target_engine.schema import TargetBounds
from afre.targets import TargetType
from afre.time import DAY_NS
from examples.feature_store_demo import UNIVERSE, clocks, origin
from examples.target_demo import SOURCE_MARKET, bar, definition
from tests.feature_store.test_availability import TEN, qualified
from tests.target_engine.test_builders import append, build, calendar


def test_known_by_filters_exact_origin_cutoff_dataset_and_vintages(
    engine: TargetEngine,
) -> None:
    append(engine, bar(1, 100.0), bar(5, 105.0))
    source = engine.freeze_source(SOURCE_MARKET, calendar(engine), 7)
    targets = TargetSetManifest((definition(),))
    origins = (
        origin(1),
        replace(origin(1), build_context="different-build"),
        replace(origin(1), availability_cutoff_ns=0),
    )
    dataset = engine.build_dataset(
        "query", origins, targets, source.fingerprint, UNIVERSE, clocks(7)
    )
    all_rows = engine.rows(dataset)
    assert not engine.targets_known_by(6, targets)
    assert set(engine.targets_known_by(7, targets)) == set(all_rows)
    exact = engine.targets_known_by(7, targets, origins=(origins[1],))
    assert len(exact) == 1 and exact[0].origin == origins[1]
    assert (
        engine.targets_known_by(7, targets, instruments=(InstrumentId("security", "absent"),))
        == ()
    )
    assert set(engine.targets_known_by(7, targets, dataset_id=dataset.fingerprint)) == set(
        all_rows
    )
    revised = replace(
        bar(5, 110.0), clocks=clocks(10), predecessor_id=bar(5, 105.0).fingerprint
    )
    append(engine, revised)
    new = build(engine, cutoff=10)
    assert new not in engine.targets_known_by(9, targets)
    assert new in engine.targets_known_by(10, targets)
    assert new not in engine.targets_known_by(10, targets, dataset_id=dataset.fingerprint)
    with pytest.raises(ContractError, match="dataset/set mismatch"):
        engine.targets_known_by(
            10,
            TargetSetManifest((definition(TargetType.LOG_RETURN),)),
            dataset_id=dataset.fingerprint,
        )
    excluded = engine.build_dataset(
        "excluded",
        (
            replace(
                origin(1),
                availability_cutoff_ns=0,
                instrument=InstrumentId("security", "outside"),
            ),
        ),
        targets,
        source.fingerprint,
        UNIVERSE,
        clocks(7),
    )
    row = engine.rows(excluded)[0]
    assert row.state is MissingState.NOT_APPLICABLE
    assert not engine.targets_known_by(10, targets, dataset_id=excluded.fingerprint)
    plan = engine.repository._connection.execute(
        "EXPLAIN QUERY PLAN SELECT fingerprint FROM target_vintages "
        "WHERE definition_id=? AND available_ns<=?",
        (definition().fingerprint, 7),
    ).fetchall()
    assert any("target_known_idx" in str(item) for item in plan)


def test_reconstruction_never_backdates_target_computation(engine: TargetEngine) -> None:
    later = 90 * DAY_NS + TEN
    delivery = AvailabilityEvidence(
        later, later + 1, later + 2, later + 2, TEN, TEN, AvailabilityMode.RECONSTRUCTED
    )
    append(
        engine,
        replace(bar(TEN, 100.0), clocks=delivery),
        replace(
            bar(TEN + 4, 105.0),
            clocks=replace(
                delivery, upstream_publication_ns=TEN + 4, upstream_available_ns=TEN + 4
            ),
        ),
    )
    before = build(engine, at=TEN, cutoff=TEN + 10)
    assert before.value is None
    row = build(engine, at=TEN, cutoff=later + 2)
    assert row.value == pytest.approx(0.05)
    assert row.clocks.final_available_ns == later + 2
    # Qualified source replay establishes historical source knowability while all
    # physical clocks remain later. It cannot qualify a backdated target computation.
    qualified_clocks = qualified()
    qualified_origin = replace(bar(TEN, 100.0), clocks=qualified_clocks)
    qualified_endpoint = replace(bar(TEN + 4, 105.0), clocks=qualified_clocks)
    append(engine, qualified_origin, qualified_endpoint)
    early_source = engine.freeze_source(
        SOURCE_MARKET, calendar(engine), qualified_clocks.final_available_ns
    )
    with pytest.raises(ContractError, match="input delivery/processing"):
        engine.build_dataset(
            "not-backdated",
            (origin(TEN),),
            TargetSetManifest((definition(),)),
            early_source.fingerprint,
            UNIVERSE,
            clocks(qualified_clocks.final_available_ns),
        )
    reconstructed = engine.build_dataset(
        "qualified-source",
        (origin(TEN),),
        TargetSetManifest((definition(),)),
        early_source.fingerprint,
        UNIVERSE,
        clocks(later + 2),
    )
    row = engine.rows(reconstructed)[0]
    assert row.value == pytest.approx(0.05) and row.clocks.afre_received_ns == later + 2
    assert qualified_endpoint.clocks.afre_ingested_ns > early_source.known_as_of_ns
    with pytest.raises(ContractError, match="cannot silently backdate"):
        replace(row, clocks=qualified_clocks)
    with pytest.raises(ContractError, match="source/entity mismatch"):
        replace(qualified_endpoint, instrument=InstrumentId("security", "other"))


@pytest.mark.parametrize(
    "bounds",
    [
        TargetBounds(origins=1),
        TargetBounds(instruments=1),
        TargetBounds(targets=1),
        TargetBounds(rows=1),
    ],
)
def test_build_and_query_input_bounds(engine: TargetEngine, bounds: TargetBounds) -> None:
    append(engine, bar(1, 100.0), bar(5, 105.0))
    source = engine.freeze_source(SOURCE_MARKET, calendar(engine), 7)
    targets = TargetSetManifest((definition(), definition(TargetType.LOG_RETURN)))
    origins = (origin(1), origin(2, InstrumentId("security", "other")))
    engine.repository.target_bounds = bounds
    with pytest.raises(ContractError, match="bound"):
        engine.build_dataset(
            "bounded", origins, targets, source.fingerprint, UNIVERSE, clocks(7)
        )
    if bounds.rows != 1:
        with pytest.raises(ContractError, match="bound"):
            engine.targets_known_by(
                7, targets, origins=origins, instruments=tuple(o.instrument for o in origins)
            )


def test_path_lineage_bytes_source_and_output_bounds(engine: TargetEngine) -> None:
    append(engine, *(bar(n, 100.0 + n) for n in range(1, 6)))
    row = build(engine)
    original = engine.repository.target_bounds
    for bounds in (
        TargetBounds(lineage_depth=1),
        TargetBounds(lineage_nodes=1),
        TargetBounds(serialized_bytes=len(canonical_json(row).encode())),
    ):
        engine.repository.target_bounds = bounds
        with pytest.raises(ContractError, match="bound"):
            engine.audit_target(row.fingerprint)
    engine.repository.target_bounds = TargetBounds(source_observations=1)
    with pytest.raises(ContractError, match="source observation"):
        engine.freeze_source(SOURCE_MARKET, calendar(engine), 7)
    engine.repository.target_bounds = TargetBounds(path_observations=1)
    with pytest.raises(ContractError, match="bound"):
        build(engine, definition(TargetType.REALIZED_VOLATILITY))
    engine.repository.target_bounds = original
    targets = TargetSetManifest((definition(),))
    source = engine.freeze_source(SOURCE_MARKET, calendar(engine), 7)
    manifest = engine.build_dataset(
        "two",
        (origin(1), replace(origin(1), build_context="other")),
        targets,
        source.fingerprint,
        UNIVERSE,
        clocks(7),
    )
    engine.repository.target_bounds = TargetBounds(rows=1)
    with pytest.raises(ContractError, match="row"):
        engine.rows(manifest)
    with pytest.raises(ContractError, match="row query"):
        engine.targets_known_by(7, targets)
    engine.repository.target_bounds = TargetBounds(serialized_bytes=5000)
    with pytest.raises(ContractError, match="serialized"):
        engine.targets_known_by(7, targets)


def test_unverified_and_partial_quality_never_train(engine: TargetEngine) -> None:
    append(engine, bar(1, 100.0), replace(bar(5, 105.0), quality=DataQuality.UNVERIFIED))
    row: TargetVintage = build(engine)
    assert row.value is not None and row.quality.source_quality is DataQuality.UNVERIFIED
    assert not engine.targets_known_by(7, TargetSetManifest((row.definition,)))
