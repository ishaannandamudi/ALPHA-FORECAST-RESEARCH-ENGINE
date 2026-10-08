"""Publication is not system receipt; historical reconstruction retains actual later clocks."""

from dataclasses import replace

import pytest

from afre.costs import CostComponentType, CostInputRole, CostTiming
from afre.costs.cost_inputs import input_reason
from afre.feature_store.models import AvailabilityEvidence, QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind
from afre.hashing import bytes_digest
from afre.lineage import ProvenanceRef
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from tests.costs.conftest import CostCase
from tests.costs.helpers import replace_input


def test_publication_1000_received_1002_origin_1001(case: CostCase) -> None:
    old = next(
        i
        for i in case.fixture.inputs
        if i.component is CostComponentType.CUSTOM_COST and i.role is CostInputRole.MODEL_VALUE
    )
    sample = next(
        s
        for s in case.repo.partition_samples(
            case.fixture.scenario.fold_id,
            Partition.VALIDATION,
        )
        if s.security.instrument == old.security
    )
    assert sample.origin is not None
    origin = replace(
        sample.origin, timestamp_ns=old.as_of_ns + 1, availability_cutoff_ns=old.as_of_ns + 1
    )
    late = replace(
        old,
        clocks=AvailabilityEvidence(
            old.as_of_ns + 2,
            old.as_of_ns + 2,
            old.as_of_ns + 2,
            old.as_of_ns + 2,
            upstream_publication_ns=old.as_of_ns,
            upstream_available_ns=old.as_of_ns,
        ),
        revision="late",
    )
    case.engine.publish_input(late)
    s = replace(case.fixture.scenario, maximum_input_age_ns=10)
    assert input_reason(case.repo, late, s, origin, 100) == "cost-not-known-at-origin"
    assert (
        input_reason(
            case.repo, late, replace(s, timing=CostTiming.EX_POST_RESEARCH), origin, 100
        )
        is None
    )


@pytest.mark.parametrize("qualified", [False, True])
def test_archive_delivery_evidence(case: CostCase, qualified: bool) -> None:
    old = next(
        i
        for i in case.fixture.inputs
        if i.component is CostComponentType.CUSTOM_COST and i.role is CostInputRole.MODEL_VALUE
    )
    at = old.as_of_ns
    evidence = (
        QualifiedHistoricalDelivery(
            old.source.fingerprint,
            old.security,
            DeliveryEvidenceKind.QUALIFIED_CHANNEL_REPLAY,
            at,
            at,
            at,
            10_000,
            "neutral-delivery-auditor",
            "qualified-historical-channel",
            "1",
            ProvenanceRef(
                "neutral-delivery-auditor",
                "delivery-proof",
                "1",
                bytes_digest(b"qualified-delivery"),
            ),
        )
        if qualified
        else None
    )
    clocks = AvailabilityEvidence(
        10_000,
        10_000,
        10_000,
        at if qualified else 10_000,
        upstream_publication_ns=at,
        upstream_available_ns=at,
        mode=AvailabilityMode.RECONSTRUCTED,
        historical_delivery=evidence,
    )
    archived = replace(
        old, clocks=clocks, revision="archive-qualified" if qualified else "archive-unqualified"
    )
    s = replace_input(case, case.fixture.scenario, old.fingerprint, archived, "archive")
    s = replace(
        s, approved_delivery_attestors=("neutral-delivery-auditor",) if qualified else ()
    )
    case.engine.declare(s)
    if not qualified:
        with pytest.raises(ContractError, match="cost-not-known-at-origin"):
            case.engine.estimate(s.fingerprint, 10_000)
        ex = replace(s, scenario_id="archive-ex-post", timing=CostTiming.EX_POST_RESEARCH)
        case.engine.declare(ex)
        _, totals = case.engine.estimate(ex.fingerprint, 10_000)
        assert all(t.timing is CostTiming.EX_POST_RESEARCH for t in totals)
    else:
        path, totals = case.engine.estimate(s.fingerprint, 10_000)
        assert all(
            t.timing is CostTiming.HISTORICAL_CAUSAL and t.constructed_ns == 10_000
            for t in totals
        )
        from afre.costs import ResearchExposureChange

        change = case.repo.resolve(ResearchExposureChange, path.change_ids[0])
        total = next(t for t in totals if t.change_id == change.fingerprint)
        with pytest.raises(ContractError, match="actually available"):
            case.engine.metadata(total.fingerprint, change.origin)
        assert (
            archived.clocks.afre_received_ns == 10_000
            and archived.clocks.final_available_ns == at
        )


def test_unapproved_delivery_rejected(case: CostCase) -> None:
    old = next(
        i
        for i in case.fixture.inputs
        if i.component is CostComponentType.CUSTOM_COST and i.role is CostInputRole.MODEL_VALUE
    )
    proof = QualifiedHistoricalDelivery(
        old.source.fingerprint,
        old.security,
        DeliveryEvidenceKind.QUALIFIED_CHANNEL_REPLAY,
        old.as_of_ns,
        old.as_of_ns,
        old.as_of_ns,
        100,
        "unapproved",
        "historical",
        "1",
        ProvenanceRef("unapproved", "proof", "1", bytes_digest(b"proof")),
    )
    value = replace(
        old,
        clocks=AvailabilityEvidence(
            100,
            100,
            100,
            old.as_of_ns,
            mode=AvailabilityMode.RECONSTRUCTED,
            historical_delivery=proof,
        ),
        revision="unapproved",
    )
    s = replace_input(case, case.fixture.scenario, old.fingerprint, value, "unapproved")
    case.engine.declare(s)
    with pytest.raises(ContractError, match="unapproved"):
        case.engine.estimate(s.fingerprint, 100)


def test_cannot_compute_before_actual_receipt(case: CostCase) -> None:
    old = next(
        i
        for i in case.fixture.inputs
        if i.component is CostComponentType.CUSTOM_COST and i.role is CostInputRole.MODEL_VALUE
    )
    late = replace(old, clocks=AvailabilityEvidence(100, 100, 100, 100), revision="late")
    s = replace_input(
        case,
        replace(case.fixture.scenario, timing=CostTiming.EX_POST_RESEARCH),
        old.fingerprint,
        late,
        "actual-floor",
    )
    case.engine.declare(s)
    with pytest.raises(ContractError, match="actual cost construction"):
        case.engine.estimate(s.fingerprint, 70)
