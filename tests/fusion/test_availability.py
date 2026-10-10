"""Provider publication never substitutes for receipt or qualified delivery."""

from dataclasses import replace

import pytest

from afre.feature_store.models import AvailabilityEvidence, QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind
from afre.fusion import ExternalFusionOutput, FusionEngine, FusionObservation, FusionRepository
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from examples.fusion_fixture import FusionFixture

Case = tuple[FusionRepository, FusionFixture]


@pytest.mark.parametrize("archive", (False, True))
def test_published_earlier_but_received_after_origin(fusion_case: Case, archive: bool) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    sample = repo.get(ResearchSample, f.validation[0])
    assert sample.origin is not None
    # Relative clock 39 = publication10:00; 40 = origin10:01; 41 = receipt10:02.
    at = 10000000 if archive else 41
    definition = f.definitions[0]
    clocks = AvailabilityEvidence(
        at,
        at,
        at,
        at,
        39,
        39,
        AvailabilityMode.RECONSTRUCTED if archive else AvailabilityMode.LIVE,
    )
    output = ExternalFusionOutput(
        definition.fingerprint,
        sample.fingerprint,
        sample.origin,
        0.1,
        None,
        clocks,
        "downloaded-later",
    )
    e.external(definition, (output,))
    ref = e.source(output.fingerprint)
    with pytest.raises(ContractError, match="unavailable at origin"):
        e.observe(ref.fingerprint, output.fingerprint)
    with pytest.raises(ContractError, match="backdated"):
        replace(clocks, final_available_ns=39)


def test_qualified_reconstruction_retains_actual_receipt(fusion_case: Case) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    sample = repo.get(ResearchSample, f.validation[0])
    assert sample.origin is not None
    definition = f.definitions[0]
    proof = QualifiedHistoricalDelivery(
        definition.source.fingerprint,
        sample.origin.instrument,
        DeliveryEvidenceKind.QUALIFIED_CHANNEL_REPLAY,
        39,
        39,
        39,
        9999999,
        "approved-archive",
        "historical-neutral-channel",
        "1",
        definition.source.provenance,
    )
    clocks = AvailabilityEvidence(
        10000000, 10000001, 10000002, 39, 38, 38, AvailabilityMode.RECONSTRUCTED, proof
    )
    output = ExternalFusionOutput(
        definition.fingerprint,
        sample.fingerprint,
        sample.origin,
        0.1,
        None,
        clocks,
        "qualified-reconstruction",
    )
    e.external(definition, (output,))
    ref = e.source(output.fingerprint)
    with pytest.raises(ContractError, match="approved exact historical"):
        e.observe(ref.fingerprint, output.fingerprint)
    observed = e.observe(ref.fingerprint, output.fingerprint, ("approved-archive",))
    assert observed.available_ns == 39
    recovered = repo.get(ExternalFusionOutput, observed.output_id)
    assert recovered.clocks.afre_received_ns == 10000000
    assert recovered.clocks.historical_delivery == proof
    assert repo.resolve(FusionObservation, observed.fingerprint) == observed


def test_external_base_in_sample_is_rejected(fusion_case: Case) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    sample = repo.get(ResearchSample, f.train[0])
    assert sample.origin is not None
    definition = replace(
        f.definitions[0],
        logical_id="in-sample",
        protocol="external-out-of-sample-v1",
        base_train_sample_ids=(sample.fingerprint,),
        base_fit_cutoff_ns=1,
    )
    raw = ExternalFusionOutput(
        definition.fingerprint,
        sample.fingerprint,
        sample.origin,
        0.1,
        None,
        AvailabilityEvidence(
            sample.timestamp_ns, sample.timestamp_ns, sample.timestamp_ns, sample.timestamp_ns
        ),
        "1",
    )
    e.external(definition, (raw,))
    ref = e.source(raw.fingerprint)
    with pytest.raises(ContractError, match="out-of-sample"):
        e.observe(ref.fingerprint, raw.fingerprint)
