"""Publication is not receipt; qualified reconstruction keeps actual clocks honest."""

from dataclasses import replace

import pytest

from afre.feature_store.models import AvailabilityEvidence, QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind
from afre.hashing import bytes_digest
from afre.lineage import ProvenanceRef
from afre.schema import ContractError
from afre.service.lineage import lineage_for
from examples.feature_store_demo import SECURITY, SOURCE, definition, source_vintage
from tests.service.conftest import ServiceCase


def test_live_and_archive_clocks(service_case: ServiceCase) -> None:
    c = service_case
    feature = definition("market.service_receipt")
    # 10:00 publication, 10:02 system receipt. 10:01 must exclude it.
    live = AvailabilityEvidence(602, 602, 602, 602, 600, 600)
    vintage = replace(source_vintage(feature, 600, 602), clocks=live)
    assert vintage.clocks.final_available_ns > 601
    with pytest.raises(ContractError, match="receipt|available|ingestion"):
        AvailabilityEvidence(602, 602, 602, 600, 600, 600)
    # Downloading an old archive months later does not make its publication causal.
    archive = AvailabilityEvidence(
        1000000, 1000000, 1000000, 1000000, 600, 600, AvailabilityMode.RECONSTRUCTED
    )
    assert archive.final_available_ns > 601 and archive.historical_delivery is None
    evidence = ProvenanceRef(
        "qualified-provider", "delivery-channel-contract", "1", bytes_digest(b"logs")
    )
    proof = QualifiedHistoricalDelivery(
        SOURCE.fingerprint,
        SECURITY,
        DeliveryEvidenceKind.QUALIFIED_CHANNEL_REPLAY,
        600,
        600,
        600,
        900000,
        "trusted-attestor",
        "delivered-feed",
        "1",
        evidence,
    )
    qualified = AvailabilityEvidence(
        1000000, 1000000, 1000000, 600, 600, 600, AvailabilityMode.RECONSTRUCTED, proof
    )
    reconstructed = replace(vintage, clocks=qualified)
    with c.repo.transaction():
        c.repo.put(feature)
        c.repo.put(proof)
        c.repo.put(reconstructed)
    with c.repo.request():
        graph = lineage_for(c.repo, reconstructed.fingerprint, ())
    assert proof.fingerprint in graph.reconstruction_evidence_ids
    assert reconstructed.clocks.afre_received_ns == 1000000
    assert reconstructed.clocks.afre_ingested_ns == 1000000
    assert reconstructed.clocks.final_available_ns == 600
