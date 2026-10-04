from dataclasses import replace

import pytest

from afre.feature_store import FeatureStore
from afre.feature_store.providers import (
    BarTimestampConvention,
    EIEFeatureAdapter,
    MarketBar,
    MarketFeatureAdapter,
    SuppliedEIEFeatures,
)
from afre.features import MissingState
from afre.providers import EventSnapshotRef
from afre.schema import ContractError
from afre.time import TimeRange
from examples.feature_store_demo import (
    BUILD,
    CALENDAR,
    INPUT_ID,
    SECURITY,
    SOURCE,
    clocks,
    definition,
    origin,
)
from tests.feature_store.test_queries import append


def test_completed_bar_timestamp_context_and_revision(store: FeatureStore) -> None:
    feature = definition()
    for index, convention in enumerate(BarTimestampConvention):
        end = 5 + index
        bar = MarketBar(
            SECURITY,
            TimeRange(1, end),
            1 if convention is BarTimestampConvention.OPEN else end,
            convention,
            100.0,
            1000.0,
            clocks(end + 1),
            SOURCE,
            feature.adjustment,
            CALENDAR,
            BUILD,
        )
        value = MarketFeatureAdapter().extract(bar, feature)
        append(store, bar, value.source, value)
        assert store.feature_as_of(feature, origin(4)).selected is None
        assert store.feature_as_of(feature, origin(end + 1)).selected == value
    with pytest.raises(ContractError):
        replace(bar, timestamp_ns=2)
    with pytest.raises(ContractError):
        replace(bar, clocks=clocks(4))
    with pytest.raises(ContractError):
        replace(bar, close=0.0)
    with pytest.raises(ContractError):
        MarketFeatureAdapter().extract(replace(bar, calendar_id="other"), feature)
    volume = definition("market.volume", "shares")
    append(store, volume)
    extracted = MarketFeatureAdapter().extract(bar, volume)
    append(store, extracted.source, extracted)
    selected = store.feature_as_of(volume, origin(end + 1)).selected
    assert selected is not None and selected.value == 1000.0
    with pytest.raises(ContractError):
        MarketFeatureAdapter().extract(bar, definition("market.unknown"))


def test_eie_delivery_reprocessing_and_metadata(store: FeatureStore) -> None:
    feature = definition("eie.event_materiality", "ratio")
    snapshot = EventSnapshotRef(
        SECURITY, "eie-final-1", 10, 10, "eie-v1", ("schema-1",), (SOURCE.provenance,)
    )
    supplied = SuppliedEIEFeatures(snapshot, 10, 0.7, 0.1, 0.2, ("uncertain_source",))
    physical = replace(clocks(12), upstream_publication_ns=10, upstream_available_ns=10)
    value = EIEFeatureAdapter().extract(supplied, feature, physical, INPUT_ID)
    append(store, feature, supplied, value.source, value)
    assert store.feature_as_of(feature, origin(11)).selected is None
    selected = store.feature_as_of(feature, origin(12)).selected
    assert selected is not None and selected.source.event_snapshot == snapshot
    assert selected.source.uncertainty_categories == ("uncertain_source",)
    revised_snapshot = replace(
        snapshot, snapshot_id="eie-final-2", known_as_of_ns=20, available_ns=20
    )
    revised = EIEFeatureAdapter().extract(
        replace(supplied, snapshot=revised_snapshot, materiality=0.9),
        feature,
        replace(clocks(22), upstream_available_ns=20),
        INPUT_ID,
    )
    append(store, revised.source, revised)
    assert store.feature_as_of(feature, origin(12)).selected == value
    assert store.feature_as_of(feature, origin(22)).selected == revised
    absent = EIEFeatureAdapter().extract(
        replace(supplied, materiality=None), feature, physical, INPUT_ID
    )
    assert absent.state is MissingState.UNKNOWN and absent.value is None
    for name in ("eie.information_surprise", "eie.event_novelty"):
        other = EIEFeatureAdapter().extract(
            supplied, definition(name, "ratio"), physical, INPUT_ID
        )
        assert other.value is not None
    for invalid in (clocks(12), replace(clocks(12), upstream_available_ns=9)):
        with pytest.raises(ContractError):
            EIEFeatureAdapter().extract(supplied, feature, invalid, INPUT_ID)
    with pytest.raises(ContractError):
        EIEFeatureAdapter().extract(
            supplied, definition("eie.unsupported", "ratio"), physical, INPUT_ID
        )
    target_component = replace(SOURCE.provenance, artifact_id="afre.target_row:1.0:" + "a" * 64)
    with pytest.raises(ContractError):
        replace(value.source, event_snapshot=replace(snapshot, components=(target_component,)))
