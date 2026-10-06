"""Receipt clocks, immutable corrections, strict guards and held-out isolation."""

from dataclasses import replace
from typing import TypeVar
from unittest.mock import patch

import pytest

from afre.cross_sectional.engine import CrossSectionEngine
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.schema import SignalQuality
from afre.feature_store.models import AvailabilityEvidence, QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind
from afre.orthogonalization import (
    PredictiveModelPair,
    ProjectionPreprocessing,
    SignalObservation,
)
from afre.orthogonalization.sources import reference_for
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import DesignMatrix
from afre.target_engine.models import TargetVintage
from examples.orthogonalization_fixture import generic_source
from tests.orthogonalization.conftest import Case

A = TypeVar("A", bound=Artifact)


def test_target_free_and_cache_guard(case: Case) -> None:
    f = case.fixture
    residual = f.residuals[0]
    original = case.repo.get

    def denied(cls: type[A], identity: str) -> A:
        if cls in (TargetVintage, DesignMatrix, PredictiveModelPair):
            raise AssertionError("residual application touched forecast truth")
        return original(cls, identity)

    with patch.object(case.repo, "get", denied):
        assert (
            case.engine.residual(
                f.projection.fingerprint, residual.row_id, residual.computed_ns
            )
            == residual
        )
        assert (
            case.engine.fit(
                f.spec, tuple(r.fingerprint for r in f.partition(Partition.TRAIN)), 40
            )
            == f.projection
        )
    pair = case.engine.fit_target_models(f.projection.fingerprint, 40)
    with case.repo.read_snapshot(), case.repo.validation_cache():
        case.repo.resolve(PredictiveModelPair, pair.fingerprint)
        with case.repo.feature_only():
            for cls, identity in (
                (PredictiveModelPair, pair.fingerprint),
                (TargetVintage, pair.target_ids[0]),
            ):
                with pytest.raises(ContractError):
                    case.repo.get_any(identity)
                with pytest.raises(ContractError):
                    case.repo.get(cls, identity)
                with pytest.raises(ContractError):
                    case.repo.resolve(cls, identity)


@pytest.mark.parametrize("late", [1, 2, 100_000_000])
def test_provider_publication_is_not_receipt(case: Case, late: int) -> None:
    row = case.fixture.partition(Partition.VALIDATION)[0]
    sample = case.repo.get(ResearchSample, row.sample_id)
    ref = case.fixture.spec.references[0]
    source = case.engine.publish_generic(generic_source(ref, sample, 1.0, "late", late))
    assert source.clocks.upstream_publication_ns == row.origin.timestamp_ns
    assert source.clocks.afre_received_ns > row.origin.availability_cutoff_ns
    with pytest.raises(ContractError, match="unavailable"):
        case.engine.bind(ref, source.fingerprint, row.sample_id)
    with pytest.raises(ContractError, match="backdated"):
        replace(source.clocks, final_available_ns=row.origin.timestamp_ns)


def test_archive_and_qualified_reconstruction(case: Case) -> None:
    row = case.fixture.partition(Partition.VALIDATION)[0]
    sample = case.repo.get(ResearchSample, row.sample_id)
    ref = case.fixture.spec.references[0]
    archive = generic_source(ref, sample, 2.0, "archive", 100_000_000)
    archive = replace(
        archive, clocks=replace(archive.clocks, mode=AvailabilityMode.RECONSTRUCTED)
    )
    case.engine.publish_generic(archive)
    with pytest.raises(ContractError):
        case.engine.bind(ref, archive.fingerprint, row.sample_id)
    proof = QualifiedHistoricalDelivery(
        archive.source.fingerprint,
        row.origin.instrument,
        DeliveryEvidenceKind.QUALIFIED_CHANNEL_REPLAY,
        row.origin.timestamp_ns,
        row.origin.timestamp_ns,
        row.origin.timestamp_ns,
        archive.clocks.afre_computed_ns,
        "independent-attestor",
        "qualified-channel",
        "1",
        archive.source.provenance,
    )
    qualified = replace(
        archive,
        clocks=replace(
            archive.clocks,
            historical_delivery=proof,
            final_available_ns=row.origin.timestamp_ns,
        ),
    )
    case.engine.publish_generic(qualified)
    with pytest.raises(ContractError, match="approved"):
        case.engine.bind(ref, qualified.fingerprint, row.sample_id)
    obs = case.engine.bind(ref, qualified.fingerprint, row.sample_id, (proof.attestor,))
    assert obs.available_ns == row.origin.timestamp_ns
    assert qualified.clocks.afre_ingested_ns > obs.available_ns
    assert qualified.clocks.historical_delivery == proof
    with pytest.raises(ContractError):
        replace(
            qualified,
            source=replace(
                archive.source,
                provenance=replace(archive.source.provenance, artifact_id="different-source"),
            ),
        )


@pytest.mark.parametrize("computed", [0, 39, 49, 51, 100])
def test_actual_residual_clock(case: Case, computed: int) -> None:
    row = case.fixture.partition(Partition.VALIDATION)[0]
    with pytest.raises(ContractError):
        case.engine.residual(case.fixture.projection.fingerprint, row.fingerprint, computed)


def test_late_projection_not_usable(case: Case) -> None:
    train = tuple(r.fingerprint for r in case.fixture.partition(Partition.TRAIN))
    p = case.engine.fit(case.fixture.spec, train, 51)
    row = case.fixture.partition(Partition.VALIDATION)[0]
    with pytest.raises(ContractError):
        case.engine.residual(p.fingerprint, row.fingerprint, 50)


def test_corrected_signal_old_bytes_and_new_identity(case: Case) -> None:
    f = case.fixture
    row = f.partition(Partition.VALIDATION)[0]
    old = next(v for v in f.residuals if v.row_id == row.fingerprint)
    before = canonical_json(old)
    sample = case.repo.get(ResearchSample, row.sample_id)
    late = case.engine.publish_generic(
        generic_source(f.spec.candidate, sample, 99.0, "correction-observed-later", 1)
    )
    with pytest.raises(ContractError):
        case.engine.bind(f.spec.candidate, late.fingerprint, row.sample_id)
    laterrow = f.partition(Partition.TEST)[0]
    later = case.repo.get(ResearchSample, laterrow.sample_id)
    revised = case.engine.publish_generic(
        generic_source(f.spec.candidate, later, 99.0, "corrected-next-origin")
    )
    obs = case.engine.bind(f.spec.candidate, revised.fingerprint, laterrow.sample_id)
    ids = tuple(
        obs.fingerprint
        if case.repo.get(SignalObservation, i).reference_id == f.spec.candidate.fingerprint
        else i
        for i in laterrow.observation_ids
    )
    newrow = case.engine.align(f.spec, ids)
    new = case.engine.residual(
        f.projection.fingerprint, newrow.fingerprint, laterrow.origin.timestamp_ns
    )
    assert new.fingerprint != old.fingerprint
    assert canonical_json(case.repo.get_any(old.fingerprint)) == before


def test_standardization_and_holdout_isolation(case: Case) -> None:
    f = case.fixture
    spec = replace(f.spec, preprocessing=ProjectionPreprocessing.TRAIN_STANDARDIZE)
    rows = tuple(case.engine.align(spec, r.observation_ids) for r in f.rows)
    train = tuple(r.fingerprint for r in rows if r.partition is Partition.TRAIN)
    model = case.engine.fit(spec, train, 40)
    frozen = canonical_json(model)
    for row in rows:
        if row.partition is Partition.TRAIN:
            continue
        sample = case.repo.get(ResearchSample, row.sample_id)
        ids = []
        for ref in (spec.candidate, *spec.references):
            src = case.engine.publish_generic(
                generic_source(ref, sample, 999.0, "perturbed-heldout")
            )
            ids.append(case.engine.bind(ref, src.fingerprint, row.sample_id).fingerprint)
        changed = case.engine.align(spec, tuple(ids))
        case.engine.residual(model.fingerprint, changed.fingerprint, row.origin.timestamp_ns)
    assert canonical_json(case.engine.fit(spec, train, 40)) == frozen
    with pytest.raises(ContractError):
        case.engine.fit(spec, tuple(r.fingerprint for r in rows), 100)


@pytest.mark.parametrize(
    "name", ["microstructure.liquidity", "mce.context", "options.implied_volatility"]
)
def test_neutral_external_sources(case: Case, name: str) -> None:
    row = case.fixture.partition(Partition.VALIDATION)[0]
    sample = case.repo.get(ResearchSample, row.sample_id)
    generic = generic_source(case.fixture.spec.candidate, sample, 0.25)
    source = generic.source
    signal = ExternalSignal(
        source.provenance.system,
        source.provenance.source_version,
        "1.0",
        sample.security,
        name,
        "1",
        "declared-neutral-scalar",
        sample.timestamp_ns,
        generic.clocks,
        0.25,
        "unit",
        SignalQuality.VALID,
        source,
    )
    identity = CrossSectionEngine(case.repo).publish_external(signal)
    ref = reference_for(case.repo, identity, sample.fingerprint, name)
    assert case.engine.bind(ref, identity, sample.fingerprint).value == 0.25
    assert ref.source_type.value == "external"
    late = replace(
        signal,
        clocks=AvailabilityEvidence(
            100, 100, 100, 100, upstream_publication_ns=sample.timestamp_ns
        ),
    )
    late_id = CrossSectionEngine(case.repo).publish_external(late)
    with pytest.raises(ContractError):
        case.engine.bind(ref, late_id, sample.fingerprint)


@pytest.mark.parametrize("mismatch", ["sample", "reference", "duplicate", "fold", "target"])
def test_exact_alignment(case: Case, mismatch: str) -> None:
    f = case.fixture
    row = f.rows[0]
    with pytest.raises((ContractError, KeyError)):
        if mismatch == "sample":
            case.engine.align(
                f.spec, (*row.observation_ids[:-1], f.rows[1].observation_ids[-1])
            )
        elif mismatch == "reference":
            case.engine.align(f.spec, row.observation_ids[:-1])
        elif mismatch == "duplicate":
            case.engine.align(f.spec, (row.observation_ids[0],) * len(row.observation_ids))
        elif mismatch == "fold":
            case.engine.align(
                replace(f.spec, fold_id=f.spec.fold_id.replace(f.spec.fold_id[-1], "0")),
                row.observation_ids,
            )
        else:
            case.engine.align(
                replace(f.spec, target=replace(f.spec.target, name="target.other")),
                row.observation_ids,
            )


def test_internal_application_requires_guard(case: Case) -> None:
    from afre.orthogonalization.residualization import residual_for

    value = case.fixture.residuals[0]
    with pytest.raises(ContractError, match="guard"):
        residual_for(case.repo, value.projection_id, value.row_id, value.computed_ns)
    with case.repo.feature_only():
        assert (
            residual_for(case.repo, value.projection_id, value.row_id, value.computed_ns)
            == value
        )


def test_publication_ten_receipt_twelve_origin_eleven(case: Case) -> None:
    from afre.orthogonalization import SignalObservation

    row = case.fixture.partition(Partition.VALIDATION)[0]
    minute = 60_000_000_000
    publication = 10 * 60 * minute
    origin_time = publication + minute
    receipt = publication + 2 * minute
    origin = replace(row.origin, timestamp_ns=origin_time, availability_cutoff_ns=origin_time)
    clocks = AvailabilityEvidence(
        receipt, receipt, receipt, receipt, upstream_publication_ns=publication
    )
    with pytest.raises(ContractError, match="unavailable"):
        SignalObservation(
            case.fixture.spec.candidate.fingerprint,
            row.observation_ids[0],
            row.sample_id,
            origin,
            1.0,
            case.fixture.residuals[0].quality,
            clocks.final_available_ns,
        )
