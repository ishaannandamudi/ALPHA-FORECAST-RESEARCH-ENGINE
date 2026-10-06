"""Receipt floors and qualified historical reconstruction preserve distinct clocks."""

from dataclasses import replace

import pytest

from afre.cross_sectional.engine import CrossSectionEngine
from afre.cross_sectional.external import ExternalSignal
from afre.feature_store.models import AvailabilityEvidence, QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind
from afre.lineage import ProvenanceRef
from afre.nonlinear import NonlinearEngine, ScalarInput
from afre.regime_conditioned.regimes import RegimeSnapshot
from afre.regime_conditioned.schema import RegimeStateSemantics
from afre.schema import ContractError
from afre.sequence import SequenceObservation, SequenceWindowMode, SequenceWindowSpec
from tests.sequence.conftest import Case


@pytest.mark.parametrize("received", [62, 10_000_000])
def test_publication_not_afre_receipt(case: Case, received: int) -> None:
    observed = case.observe(60, 2.0, received=received)
    origin = replace(case.forecast.origin, timestamp_ns=61, availability_cutoff_ns=61)
    snap = case.engine.snapshot(
        origin,
        (case.micro,),
        SequenceWindowSpec(SequenceWindowMode.FIXED_OBSERVATION_COUNT, 2),
        received,
        (observed.fingerprint,),
    )
    assert snap.effective_counts == (0,)
    assert (observed.fingerprint, "future-availability") in snap.exclusions
    with pytest.raises(ContractError, match="backdated"):
        AvailabilityEvidence(received, received, received, 60, 60, 60)


def test_qualified_archive_not_fake_historical_ingestion(case: Case) -> None:
    f = case.forecast
    old = next(
        case.repo.get(SequenceObservation, i)
        for i in case.fixture.observation_ids
        if case.repo.get(SequenceObservation, i).feature_id == case.micro.fingerprint
        and case.repo.get(SequenceObservation, i).security == f.origin.instrument
    )
    scalar = case.repo.get(ScalarInput, old.source_id)
    source = case.repo.get(ExternalSignal, scalar.source_id)
    proof = QualifiedHistoricalDelivery(
        source.source.fingerprint,
        f.origin.instrument,
        DeliveryEvidenceKind.AFRE_DELIVERY_LOG,
        55,
        55,
        55,
        1_000_000,
        "approved-lab",
        "delivery-log",
        "1",
        ProvenanceRef("lab", "receipt-log", "1", "0" * 64),
    )
    reconstructed = replace(
        source,
        as_of_ns=55,
        value=3.0,
        clocks=AvailabilityEvidence(
            1_000_000, 1_000_000, 1_000_000, 55, 55, 55, AvailabilityMode.RECONSTRUCTED, proof
        ),
    )
    CrossSectionEngine(case.repo).publish_external(reconstructed)
    with pytest.raises(ContractError, match="unapproved"):
        NonlinearEngine(case.repo).scalar(reconstructed.fingerprint, f.origin)
    qualified = NonlinearEngine(case.repo).scalar(
        reconstructed.fingerprint, f.origin, approved_attestors=("approved-lab",)
    )
    observation = case.engine.observation(case.micro, qualified.fingerprint)
    snap = case.engine.snapshot(
        f.origin, case.fixture.features, case.fixture.specs[0].window, 1_000_000
    )
    from afre.research_datasets.samples import ResearchSample
    from afre.sequence.datasets import validate_snapshot_input

    sample = case.repo.get(ResearchSample, f.sample_id)
    with pytest.raises(ContractError, match="unapproved"):
        validate_snapshot_input(case.repo, case.fixture.specs[0], sample, snap)
    assert observation.fingerprint in {i for row in snap.observation_ids for i in row}
    from afre.research_datasets.schema import Partition

    assert (
        validate_snapshot_input(
            case.repo,
            replace(case.fixture.specs[0], approved_delivery_attestors=("approved-lab",)),
            sample,
            snap,
        )
        is Partition.VALIDATION
    )
    assert observation.afre_ready_ns == 1_000_000 and snap.available_ns == 1_000_000
    with pytest.raises(ContractError, match="candidate evidence unavailable"):
        case.engine.snapshot(
            f.origin,
            (case.micro,),
            case.fixture.specs[0].window,
            60,
            (observation.fingerprint,),
        )
    assert observation.available_ns == 55
    assert reconstructed.clocks.afre_received_ns == 1_000_000
    assert reconstructed.clocks.historical_delivery == proof


def test_smoothed_regime_never_enters(case: Case) -> None:
    source = next(
        case.repo.get_any(
            case.repo.get(
                ScalarInput, case.repo.get(SequenceObservation, i).source_id
            ).source_id
        )
        for i in case.fixture.observation_ids
        if case.repo.get(SequenceObservation, i).source_id.startswith("afre.nl_scalar:")
        and case.repo.get(
            ScalarInput, case.repo.get(SequenceObservation, i).source_id
        ).definition.kind.value
        == "regime_probability"
    )
    assert isinstance(source, RegimeSnapshot)
    for kind in (RegimeStateSemantics.SMOOTHED, RegimeStateSemantics.EX_POST):
        with pytest.raises(ContractError):
            revised = replace(source, semantics=kind)
            NonlinearEngine(case.repo).scalar(revised.fingerprint, case.forecast.origin)
