"""Historical-delivery qualification and causal audit features never backdate receipt."""

from dataclasses import replace

import pytest

from afre.feature_store.models import FeatureVintage, QualifiedHistoricalDelivery
from afre.feature_store.schema import AvailabilityMode, DeliveryEvidenceKind
from afre.mixture import (
    ExpertForecastBinding,
    ExpertMissingPolicy,
    ExternalExpertForecast,
    FixedGateSpec,
    GatingFeatureReference,
    MixtureForecast,
)
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from tests.mixture.conftest import Case
from tests.mixture.test_temporal import request_for


def test_archive_needs_local_qualified_delivery_evidence(case: Case) -> None:
    request = request_for(case, ExpertMissingPolicy.DROP_AND_RENORMALIZE)
    expert_id, binding_id = request.expert_inputs[0]
    binding = case.repo.get(ExpertForecastBinding, binding_id or "")
    raw = case.repo.get(ExternalExpertForecast, binding.forecast_id)
    archive = replace(
        raw,
        clocks=replace(
            raw.clocks,
            mode=AvailabilityMode.RECONSTRUCTED,
            afre_received_ns=100000,
            afre_ingested_ns=100000,
            afre_computed_ns=100000,
            final_available_ns=100000,
        ),
    )
    archive_binding = case.engine.bind(expert_id, case.engine.publish_external(archive))
    archived = case.engine.forecast(
        replace(
            request,
            expert_inputs=((expert_id, archive_binding.fingerprint), request.expert_inputs[1]),
        )
    )
    assert archived.contributions[0].reason == "not-available-by-origin"
    proof = QualifiedHistoricalDelivery(
        raw.source.fingerprint,
        raw.origin.instrument,
        DeliveryEvidenceKind.AFRE_DELIVERY_LOG,
        raw.as_of_ns,
        raw.as_of_ns,
        raw.as_of_ns,
        100000,
        "local-review",
        "recorded-channel",
        "1",
        raw.source.provenance,
    )
    qualified = replace(
        archive,
        clocks=replace(
            archive.clocks, historical_delivery=proof, final_available_ns=raw.as_of_ns
        ),
    )
    qualified_binding = case.engine.bind(expert_id, case.engine.publish_external(qualified))
    new_request = replace(
        request,
        expert_inputs=((expert_id, qualified_binding.fingerprint), request.expert_inputs[1]),
    )
    unapproved = case.engine.forecast(new_request)
    assert unapproved.contributions[0].reason == "unqualified-historical-delivery"
    old_gate = case.repo.get(FixedGateSpec, request.gate_id)
    approved = replace(
        old_gate,
        expert_set=replace(old_gate.expert_set, approved_delivery_attestors=("local-review",)),
    )
    case.engine.publish_gate(approved)
    result = case.engine.forecast(
        replace(
            new_request,
            gate_id=approved.fingerprint,
            expert_set_id=approved.expert_set.fingerprint,
        )
    )
    assert result.contributions[0].reason == "available"
    assert (
        qualified.clocks.afre_received_ns == 100000
        and qualified.clocks.final_available_ns == raw.as_of_ns
    )
    with pytest.raises(ContractError, match="source/entity"):
        replace(
            qualified,
            source=replace(
                raw.source, provenance=replace(raw.source.provenance, source_version="wrong")
            ),
        )


def test_causal_features_pinned_in_train_and_application(case: Case) -> None:
    rows = case.fixture.learned.rows
    feature_names = tuple(
        case.repo.get(FeatureVintage, i).feature.definition.fingerprint
        for i in case.repo.get(ResearchSample, rows[0].sample_id).feature_vintage_ids
    )
    spec = replace(case.fixture.learned_spec, gating_feature_ids=feature_names)
    trained = []
    for row in reversed(rows):
        sample = case.repo.get(ResearchSample, row.sample_id)
        assert sample.origin is not None
        features = []
        for identity in reversed(sample.feature_vintage_ids):
            vintage = case.repo.get(FeatureVintage, identity)
            feature = GatingFeatureReference(
                vintage.feature.definition.fingerprint,
                identity,
                sample.origin,
                vintage.clocks.final_available_ns,
                float(vintage.value or 0.0),
            )
            features.append(case.engine.publish_gating_feature(feature))
        trained.append(
            case.engine.training_row(
                spec, row.sample_id, tuple(reversed(row.binding_ids)), tuple(reversed(features))
            ).fingerprint
        )
    model = case.engine.fit(spec, tuple(trained), 40, 40, 40)
    assert model.weights == case.fixture.learned.weights
    forecast = next(
        case.repo.get(MixtureForecast, i)
        for i in case.fixture.learned_ids
        if case.repo.get(MixtureForecast, i).origin.timestamp_ns == 60
    )
    sample = case.repo.get(ResearchSample, forecast.request.sample_id)
    assert sample.origin is not None
    ids = []
    for identity in sample.feature_vintage_ids:
        vintage = case.repo.get(FeatureVintage, identity)
        f = GatingFeatureReference(
            vintage.feature.definition.fingerprint,
            identity,
            sample.origin,
            vintage.clocks.final_available_ns,
            float(vintage.value or 0.0),
        )
        ids.append(case.engine.publish_gating_feature(f))
    request = replace(
        forecast.request, gate_id=model.fingerprint, gating_feature_ids=tuple(ids)
    )
    result = case.engine.forecast(request)
    assert result.value == forecast.value
    assert (
        case.engine.forecast(replace(request, gating_feature_ids=tuple(reversed(ids))))
        == result
    )
    with pytest.raises(ContractError, match="exact gating features"):
        case.engine.forecast(replace(request, gating_feature_ids=()))


def test_neutral_signal_and_filtered_regime_are_causal_audit_features(case: Case) -> None:
    from afre.cross_sectional import CrossSectionEngine
    from afre.regime_conditioned import RegimeEngine, RegimeSnapshot
    from examples.cross_sectional_demo import external
    from examples.regime_conditioned_demo import snapshot, taxonomy

    sample = case.sample
    assert sample.origin is not None
    signal = external(sample.security, sample.timestamp_ns, 0.2)
    CrossSectionEngine(case.repo).publish_external(signal)
    feature = GatingFeatureReference(
        signal.signal_name + ":" + signal.signal_version,
        signal.fingerprint,
        sample.origin,
        signal.clocks.final_available_ns,
        0.2,
    )
    case.engine.publish_gating_feature(feature)
    tax = taxonomy()
    re = RegimeEngine(case.repo)
    re.publish_taxonomy(tax)
    regime = snapshot(tax, sample, soft=(0.3, 0.7))
    re.publish_snapshot(regime)
    feature = GatingFeatureReference(
        regime.membership.states[0],
        regime.fingerprint,
        sample.origin,
        regime.clocks.final_available_ns,
        0.3,
    )
    case.engine.publish_gating_feature(feature)
    with pytest.raises(ContractError, match="scalar"):
        case.engine.publish_gating_feature(replace(feature, value=1.0))
    assert case.repo.get(RegimeSnapshot, regime.fingerprint) == regime


def test_native_event_and_regime_raw_probability_bindings(case: Case) -> None:
    from afre.mixture import ExpertKind, ExpertOutput
    from afre.probabilistic.distributions import expected_value

    for kind in (ExpertKind.AFRE_EVENT, ExpertKind.AFRE_REGIME):
        old = next(e for e in case.fixture.fixed.expert_set.experts if e.kind is kind)
        native = replace(
            old, expert_id=old.expert_id + "-raw", output=ExpertOutput.PROBABILISTIC
        )
        case.engine.register_expert(native)
        old_binding = next(
            case.repo.get(ExpertForecastBinding, b)
            for i, b in case.forecast.request.expert_inputs
            if i == old.fingerprint and b
        )
        binding = case.engine.bind(native.fingerprint, old_binding.forecast_id)
        assert binding.distribution is not None and binding.point == expected_value(
            binding.distribution
        )
        assert binding.sample_id == case.sample.fingerprint
