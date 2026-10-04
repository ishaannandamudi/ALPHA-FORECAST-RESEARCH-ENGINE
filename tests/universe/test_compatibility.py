from dataclasses import replace

import pytest

from afre.feature_store import FeatureSetManifest, FeatureStore
from afre.forecast import ForecastOrigin
from afre.schema import ContractError
from afre.target_engine import TargetEngine, TargetSetManifest
from afre.universe import to_universe_manifest, validate_snapshot_origin
from afre.universe.schema import SnapshotCompleteness
from examples.feature_store_demo import BUILD, clocks, dataset
from examples.target_demo import (
    CALENDAR_TARGET,
    SOURCE_MARKET,
    bar,
    definition,
    register_sources,
)
from examples.universe_demo import SECURITIES, DemoFixture


def test_exact_snapshot_projection_compatible_feature_and_target_rows(
    fixture: DemoFixture,
) -> None:
    repository = fixture.engine.repository
    manifest = to_universe_manifest(fixture.snapshot)
    origin = ForecastOrigin(
        SECURITIES[0].instrument, 30, 30, "synthetic-session-v1", BUILD, manifest.fingerprint
    )
    validate_snapshot_origin(fixture.snapshot, manifest, origin)
    features = FeatureSetManifest((fixture.price,))
    data = replace(dataset(features), universe=manifest)
    store = FeatureStore(repository)
    feature_row = store.point_in_time_join((origin,), data, features)[0].row
    assert feature_row.origin.instrument == SECURITIES[0].instrument
    assert feature_row.origin.universe_id == manifest.fingerprint
    with pytest.raises(ContractError):
        store.point_in_time_join(
            (replace(origin, instrument=SECURITIES[3].instrument),), data, features
        )
    with pytest.raises(ContractError):
        store.point_in_time_join(
            (replace(origin, universe_id="afre.universe:1.0:" + "0" * 64),), data, features
        )
    register_sources(repository)
    with repository.transaction():
        repository.put(bar(30, 100.0))
        repository.put(bar(34, 105.0))
    targets = TargetSetManifest((definition(),))
    engine = TargetEngine(repository)
    source = engine.freeze_source(SOURCE_MARKET, CALENDAR_TARGET, 34)
    target_manifest = engine.build_dataset(
        "universe-compatibility", (origin,), targets, source.fingerprint, manifest, clocks(34)
    )
    target_row = engine.rows(target_manifest)[0]
    assert target_row.origin == feature_row.origin and target_row.value == pytest.approx(0.05)
    with pytest.raises(ContractError):
        engine.build_dataset(
            "wrong-universe",
            (replace(origin, universe_id=fixture.universe.fingerprint),),
            targets,
            source.fingerprint,
            manifest,
            clocks(34),
        )
    with pytest.raises(ContractError):
        validate_snapshot_origin(
            fixture.snapshot, manifest, replace(origin, instrument=SECURITIES[3].instrument)
        )
    with pytest.raises(ContractError), repository.transaction():
        repository.put(
            replace(target_row, origin=replace(origin, instrument=SECURITIES[1].instrument))
        )
    assert repository.audit() > 0


def test_uncertainty_and_later_knowledge_cannot_be_projected(fixture: DemoFixture) -> None:
    for altered in (
        replace(fixture.snapshot, completeness=SnapshotCompleteness.UNKNOWN),
        replace(fixture.snapshot, memberships=(), eligibility=()),
    ):
        with pytest.raises(ContractError):
            to_universe_manifest(altered)
    future_known = fixture.engine.universe_as_of(fixture.universe, 30, 80)
    with pytest.raises(ContractError, match="future knowledge"):
        to_universe_manifest(future_known)
    with pytest.raises(ContractError):
        validate_snapshot_origin(
            fixture.snapshot,
            to_universe_manifest(fixture.snapshot),
            ForecastOrigin(
                SECURITIES[0].instrument,
                31,
                30,
                "synthetic-session-v1",
                BUILD,
                to_universe_manifest(fixture.snapshot).fingerprint,
            ),
        )
