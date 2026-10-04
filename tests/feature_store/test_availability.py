from dataclasses import replace
from typing import Any

import pytest

from afre.feature_store import (
    AvailabilityEvidence,
    FeatureStore,
    FeatureVintage,
    QualifiedHistoricalDelivery,
)
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind, QueryPolicy
from afre.features import DataQuality, MissingState
from afre.schema import ContractError
from afre.time import DAY_NS, SECOND_NS
from examples.feature_store_demo import (
    SECURITY,
    SOURCE,
    clocks,
    definition,
    origin,
    source_vintage,
)

TEN = 10 * 3600 * SECOND_NS
MINUTE = 60 * SECOND_NS


def test_publication_is_not_afre_availability(store: FeatureStore) -> None:
    feature = definition()
    delivery = AvailabilityEvidence(
        TEN + 2 * MINUTE, TEN + 2 * MINUTE, TEN + 2 * MINUTE, TEN + 2 * MINUTE, TEN, TEN
    )
    value = replace(source_vintage(feature, TEN, TEN + 2 * MINUTE, 10.0), clocks=delivery)
    with store.repository.transaction():
        store.append_vintage(value)
    assert store.feature_as_of(feature, origin(TEN + MINUTE)).selected is None
    assert store.feature_as_of(feature, origin(TEN + 2 * MINUTE)).selected == value
    with pytest.raises(ContractError, match="backdated"):
        replace(delivery, final_available_ns=TEN)


def test_archive_download_months_later_is_not_causal(store: FeatureStore) -> None:
    later = 90 * DAY_NS + TEN
    archived = AvailabilityEvidence(
        later, later + 1, later + 2, later + 2, TEN, TEN, AvailabilityMode.RECONSTRUCTED
    )
    value = replace(source_vintage(definition(), TEN, later + 2), clocks=archived)
    with store.repository.transaction():
        store.append_vintage(value)
    assert store.feature_as_of(definition(), origin(TEN + MINUTE)).selected is None
    assert store.feature_as_of(definition(), origin(later + 2)).selected == value
    with pytest.raises(ContractError):
        replace(archived, final_available_ns=TEN)


def qualified() -> AvailabilityEvidence:
    later = 90 * DAY_NS + TEN
    evidence = QualifiedHistoricalDelivery(
        SOURCE.fingerprint,
        SECURITY,
        DeliveryEvidenceKind.QUALIFIED_CHANNEL_REPLAY,
        TEN + MINUTE,
        TEN + MINUTE + 1,
        TEN + MINUTE + 2,
        later,
        "archive-audit-v1",
        "historical-research-channel",
        "qualification-v1",
        SOURCE.provenance,
    )
    return AvailabilityEvidence(
        later,
        later + 1,
        later + 2,
        TEN + MINUTE + 2,
        TEN,
        TEN,
        AvailabilityMode.RECONSTRUCTED,
        evidence,
    )


def test_qualified_reconstruction_preserves_actual_clocks(store: FeatureStore) -> None:
    evidence = qualified()
    value = replace(source_vintage(definition(), TEN, TEN + MINUTE + 2), clocks=evidence)
    with pytest.raises(ContractError, match="locally approved"), store.repository.transaction():
        store.append_vintage(value)
    allowed = FeatureStore(store.repository, QueryPolicy(("archive-audit-v1",)))
    with store.repository.transaction():
        allowed.append_vintage(value)
    historical = allowed.feature_as_of(definition(), origin(TEN + 2 * MINUTE))
    assert historical.selected == value
    assert historical.selected.clocks.afre_received_ns == 90 * DAY_NS + TEN
    assert historical.selected.clocks.afre_ingested_ns > historical.origin.timestamp_ns
    assert (
        historical.selected.clocks.final_available_ns
        < historical.selected.clocks.afre_received_ns
    )
    assert historical.selected.clocks.historical_delivery is not None
    assert (
        historical.selected.clocks.historical_delivery.kind
        is DeliveryEvidenceKind.QUALIFIED_CHANNEL_REPLAY
    )
    assert allowed.feature_as_of(definition(), origin(TEN)).selected is None
    with pytest.raises(ContractError, match="locally approved"):
        store.feature_as_of(definition(), origin(TEN + 2 * MINUTE))
    # No claim of historical literal AFRE receipt: the delivered reference retains all clocks.
    projection = historical.selected.to_feature_value(
        SECURITY, MissingState.PRESENT, allowed.policy.fingerprint
    )
    assert projection.observed_ns == TEN  # AFRE-0 source-observation field, never AFRE receipt.


@pytest.mark.parametrize(
    "changes",
    [
        {"afre_received_ns": 12, "afre_ingested_ns": 11},
        {"afre_ingested_ns": 12, "afre_computed_ns": 11},
        {"upstream_publication_ns": 12, "upstream_available_ns": 11},
        {"upstream_available_ns": 20},
        {"upstream_publication_ns": 20},
        {"final_available_ns": 9},
        {"afre_received_ns": True},
        {"afre_computed_ns": -1},
    ],
)
def test_clock_invariants(changes: dict[str, Any]) -> None:
    with pytest.raises(ContractError):
        replace(clocks(10), **changes)


def test_qualified_evidence_binding_and_order(store: FeatureStore) -> None:
    from afre.ids import InstrumentId

    value = replace(source_vintage(definition(), TEN, TEN + MINUTE + 2), clocks=qualified())
    proof = value.clocks.historical_delivery
    assert proof is not None
    changes: tuple[dict[str, Any], ...] = (
        {"historical_received_ns": proof.historical_computed_ns + 1},
        {"qualified_ns": proof.historical_computed_ns - 1},
    )
    for change in changes:
        with pytest.raises(ContractError):
            replace(proof, **change)
    with pytest.raises(ContractError):
        replace(value.clocks, mode=AvailabilityMode.LIVE)
    with pytest.raises(ContractError):
        replace(value.clocks, afre_computed_ns=proof.qualified_ns - 1)
    for changed in (
        replace(proof, entity=InstrumentId("issuer", "other")),
        replace(proof, source_id=replace(SOURCE, uncertainty_categories=("x",)).fingerprint),
    ):
        with pytest.raises(ContractError, match="exact source/entity"):
            replace(value, clocks=replace(value.clocks, historical_delivery=changed))
    actual_log = replace(proof, kind=DeliveryEvidenceKind.AFRE_DELIVERY_LOG)
    assert (
        replace(value.clocks, historical_delivery=actual_log).historical_delivery == actual_log
    )


def test_source_clock_only_and_reconstructed_dependency_floor() -> None:
    feature = definition()
    assert replace(clocks(10), upstream_publication_ns=5).availability_floor_ns == 10
    assert replace(clocks(10), upstream_available_ns=5).availability_floor_ns == 10
    for state in MissingState:
        value = None if state is not MissingState.PRESENT else 0.0
        vintage = FeatureVintage(
            feature, SECURITY, 0, clocks(10), SOURCE, value, state, DataQuality.VERIFIED
        )
        assert vintage.value == value
    for invalid in (float("nan"), float("inf"), True):
        with pytest.raises(ContractError):
            replace(source_vintage(feature, 0, 10), value=invalid)
