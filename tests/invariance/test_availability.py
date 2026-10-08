"""Historical knowability, actual system observation and later reconstruction stay distinct."""

from dataclasses import replace

import pytest

from afre.feature_store.models import AvailabilityEvidence, QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind
from afre.invariance import (
    EnvironmentDefinition,
    EnvironmentKind,
    EnvironmentRule,
    EnvironmentSet,
    EnvironmentState,
    NeutralEnvironmentLabel,
)
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.time import TimeRange
from examples.cross_sectional_demo import provider_source
from tests.invariance.conftest import Case


@pytest.mark.parametrize("qualified", [False, True])
def test_archive_publication_is_not_AFRE_delivery(case: Case, qualified: bool) -> None:
    s = case.repo.get(ResearchSample, case.fixture.spec.sample_ids[0])
    assert s.origin is not None
    source = provider_source("invariance-archive")
    proof = (
        QualifiedHistoricalDelivery(
            source.fingerprint,
            s.origin.instrument,
            DeliveryEvidenceKind.QUALIFIED_CHANNEL_REPLAY,
            s.timestamp_ns,
            s.timestamp_ns,
            s.timestamp_ns,
            100,
            "neutral-attestor",
            "qualified-test-channel",
            "1",
            source.provenance,
        )
        if qualified
        else None
    )
    clocks = AvailabilityEvidence(
        100,
        100,
        100,
        s.timestamp_ns if qualified else 100,
        upstream_publication_ns=s.timestamp_ns,
        upstream_available_ns=s.timestamp_ns,
        mode=AvailabilityMode.RECONSTRUCTED,
        historical_delivery=proof,
    )
    d = EnvironmentDefinition(
        "archive",
        EnvironmentKind.CUSTOM,
        "archive label",
        "1",
        source.provenance.system,
        EnvironmentRule.LABEL,
        case.fixture.spec.target,
        40,
        neutral_label="open",
        approved_delivery_attestors=("neutral-attestor",),
    )
    case.engine.declare(EnvironmentSet((d,), 40))
    label = case.engine.publish_label(
        NeutralEnvironmentLabel(
            s.fingerprint, s.origin, d.provider, "open", "1", TimeRange(0, 1000), clocks, source
        )
    )
    m = case.engine.bind(d.fingerprint, s.fingerprint, (label.fingerprint,), constructed_ns=100)
    assert m.state is (EnvironmentState.INCLUDED if qualified else EnvironmentState.UNAVAILABLE)
    assert m.available_ns == 100 and label.clocks.afre_received_ns == 100
    assert label.clocks.final_available_ns == (s.timestamp_ns if qualified else 100)
    with pytest.raises(ContractError, match="actually constructed"):
        case.engine.metadata(m.fingerprint, s.origin)
    if qualified:
        unapproved = replace(
            d, environment_id="unapproved-archive", approved_delivery_attestors=()
        )
        case.engine.declare(EnvironmentSet((unapproved,), 40))
        with pytest.raises(ContractError):
            case.engine.bind(
                unapproved.fingerprint, s.fingerprint, (label.fingerprint,), constructed_ns=100
            )
