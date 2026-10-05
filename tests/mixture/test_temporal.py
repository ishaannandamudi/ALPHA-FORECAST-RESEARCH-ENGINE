"""Receipt, feature clocks, TRAIN-only learning and target-free deployment regressions."""

from dataclasses import replace
from typing import TypeVar

import pytest

from afre.feature_store.models import FeatureVintage
from afre.mixture import (
    ExpertForecastBinding,
    ExpertMissingPolicy,
    ExpertQuality,
    GateTrainingRow,
    GatingFeatureReference,
    MixtureForecast,
    MixtureRequest,
)
from afre.mixture.experts import ExternalExpertForecast
from afre.research_datasets.samples import ResearchSample
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import DesignMatrix
from afre.target_engine.models import TargetVintage
from examples.mixture_demo import external_binding, fixed_gate
from tests.mixture.conftest import Case


def request_for(case: Case, policy: ExpertMissingPolicy, late: bool = False) -> MixtureRequest:
    experts = case.fixture.learned_spec.expert_set.experts
    fallback = (
        experts[1].fingerprint if policy is ExpertMissingPolicy.USE_DECLARED_FALLBACK else None
    )
    gate = fixed_gate(case.repo, experts, policy, fallback)
    inputs = tuple(
        (
            e.fingerprint,
            external_binding(
                case.repo,
                e,
                case.sample,
                float(index + 1),
                received=case.sample.timestamp_ns + 1 if late and index == 0 else None,
            ),
        )
        for index, e in enumerate(experts)
    )
    return replace(
        case.forecast.request,
        expert_set_id=gate.expert_set.fingerprint,
        gate_id=gate.fingerprint,
        expert_inputs=inputs,
    )


def test_same_time_final_availability_is_admitted(case: Case) -> None:
    forecast = case.engine.forecast(request_for(case, ExpertMissingPolicy.FAIL))
    assert forecast.available_ns == forecast.origin.timestamp_ns
    assert all(c.reason == "available" for c in forecast.contributions)


def test_publication_before_origin_receipt_after_origin_excluded(case: Case) -> None:
    request = request_for(case, ExpertMissingPolicy.DROP_AND_RENORMALIZE, True)
    forecast = case.engine.forecast(request)
    late = next(c for c in forecast.contributions if c.reason != "available")
    assert late.original_weight == 0.5 and late.effective_weight == 0.0
    assert late.value is None and late.contribution is None
    assert forecast.value == 2.0
    assert tuple(c.effective_weight for c in forecast.contributions) == (0.0, 1.0)


def test_late_fail_and_explicit_fallback(case: Case) -> None:
    with pytest.raises(ContractError, match="FAIL"):
        case.engine.forecast(request_for(case, ExpertMissingPolicy.FAIL, True))
    fallback = case.engine.forecast(
        request_for(case, ExpertMissingPolicy.USE_DECLARED_FALLBACK, True)
    )
    assert fallback.value == 2.0 and fallback.fallback_id is not None


@pytest.mark.parametrize("policy", list(ExpertMissingPolicy))
def test_missing_expert_has_no_implicit_zero(case: Case, policy: ExpertMissingPolicy) -> None:
    request = request_for(case, policy)
    request = replace(request, expert_inputs=tuple((i, None) for i, _ in request.expert_inputs))
    with pytest.raises(ContractError):
        case.engine.forecast(request)


@pytest.mark.parametrize(
    "quality",
    [
        ExpertQuality.MISSING,
        ExpertQuality.STALE,
        ExpertQuality.DEGRADED,
        ExpertQuality.UNSUPPORTED,
        ExpertQuality.INVALID,
    ],
)
def test_external_quality_is_explicit_missingness(case: Case, quality: ExpertQuality) -> None:
    request = request_for(case, ExpertMissingPolicy.DROP_AND_RENORMALIZE)
    expert_id, binding_id = request.expert_inputs[0]
    assert binding_id
    binding = case.repo.get(ExpertForecastBinding, binding_id)
    raw = case.repo.get(ExternalExpertForecast, binding.forecast_id)
    changed = replace(raw, quality=quality, point=None)
    changed_id = case.engine.bind(expert_id, case.engine.publish_external(changed)).fingerprint
    forecast = case.engine.forecast(
        replace(request, expert_inputs=((expert_id, changed_id), request.expert_inputs[1]))
    )
    assert forecast.contributions[0].reason == "forecast:" + quality.value
    assert forecast.contributions[0].contribution is None


def test_live_or_archive_receipt_cannot_be_backdated(case: Case) -> None:
    request = request_for(case, ExpertMissingPolicy.FAIL)
    binding = case.repo.get(ExpertForecastBinding, request.expert_inputs[0][1] or "")
    raw = case.repo.get(ExternalExpertForecast, binding.forecast_id)
    with pytest.raises(ContractError, match="backdated"):
        replace(
            raw,
            clocks=replace(
                raw.clocks,
                afre_received_ns=1000,
                afre_ingested_ns=1000,
                afre_computed_ns=1000,
                final_available_ns=raw.as_of_ns,
            ),
        )


def test_future_gate_and_computation_are_rejected(case: Case) -> None:
    learned = case.fixture.learned
    future = case.engine.fit(case.fixture.learned_spec, case.fixture.training_ids, 70, 70, 70)
    forecast = next(
        case.repo.get(MixtureForecast, i)
        for i in case.fixture.learned_ids
        if case.repo.get(MixtureForecast, i).origin.timestamp_ns == 60
    )
    with pytest.raises(ContractError, match="unavailable"):
        case.engine.forecast(replace(forecast.request, gate_id=future.fingerprint))
    with pytest.raises(ContractError, match="unavailable"):
        case.engine.forecast(replace(case.forecast.request, computed_ns=61))
    with pytest.raises(ContractError, match="unavailable"):
        case.engine.forecast(replace(case.forecast.request, computed_ns=59))
    assert canonical_json(case.fixture.learned) == canonical_json(learned)


def test_gate_rejects_validation_and_test_training_rows(case: Case) -> None:
    forecast = case.forecast
    bindings = tuple(
        b
        for i, b in forecast.request.expert_inputs
        if i in case.fixture.learned_spec.expert_set.expert_ids and b
    )
    with pytest.raises(ContractError, match="TRAIN only"):
        case.engine.training_row(
            case.fixture.learned_spec, forecast.request.sample_id, bindings
        )
    test = case.repo.get(MixtureForecast, case.fixture.test_ids[0])
    with pytest.raises(ContractError, match="TRAIN only"):
        case.engine.training_row(case.fixture.learned_spec, test.request.sample_id, bindings)


def test_gate_rejects_late_train_expert_and_unknown_label(case: Case) -> None:
    row = case.repo.get(GateTrainingRow, case.fixture.training_ids[0])
    sample = case.repo.get(ResearchSample, row.sample_id)
    experts = case.fixture.learned_spec.expert_set.experts
    bindings = tuple(
        external_binding(
            case.repo,
            e,
            sample,
            float(index),
            received=sample.timestamp_ns + 1 if index == 0 else None,
        )
        for index, e in enumerate(experts)
    )
    with pytest.raises(ContractError, match="noncausal"):
        case.engine.training_row(case.fixture.learned_spec, row.sample_id, bindings)
    with pytest.raises(ContractError, match="fit availability"):
        replace(case.fixture.learned, available_ns=39)


def test_target_free_application_and_base_immutability(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    A = TypeVar("A", bound=Artifact)
    original = case.repo.get
    before = {
        i: canonical_json(case.repo.get_any(i)) for i, _ in case.forecast.request.expert_inputs
    }

    def guarded(cls: type[A], identity: str) -> A:
        assert cls not in (TargetVintage, DesignMatrix, GateTrainingRow), (
            "deployment read TRAIN/truth"
        )
        return original(cls, identity)

    monkeypatch.setattr(case.repo, "get", guarded)
    assert case.engine.forecast(case.forecast.request) == case.forecast
    learned = next(
        case.repo.get(MixtureForecast, i)
        for i in case.fixture.learned_ids
        if case.repo.get(MixtureForecast, i).origin.timestamp_ns == 60
    )
    assert case.engine.forecast(learned.request) == learned
    assert {i: canonical_json(case.repo.get_any(i)) for i in before} == before


def test_late_gating_feature_and_false_scalar_rejected(case: Case) -> None:
    assert case.sample.origin is not None
    vintage = case.repo.get(FeatureVintage, case.sample.feature_vintage_ids[0])
    with pytest.raises(ContractError, match="unavailable"):
        GatingFeatureReference(
            vintage.feature.definition.fingerprint,
            vintage.fingerprint,
            case.sample.origin,
            case.sample.timestamp_ns + 1,
            1.0,
        )
    feature = GatingFeatureReference(
        vintage.feature.definition.fingerprint,
        vintage.fingerprint,
        case.sample.origin,
        vintage.clocks.final_available_ns,
        float(vintage.value or 0.0),
    )
    case.engine.publish_gating_feature(feature)
    with pytest.raises(ContractError, match="scalar"):
        case.engine.publish_gating_feature(replace(feature, value=feature.value + 1.0))


def test_held_out_target_perturbation_cannot_change_gate(
    case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    admitted = {r.target_id for r in case.fixture.learned.rows}
    A = TypeVar("A", bound=Artifact)
    original = case.repo.get

    def perturb(cls: type[A], identity: str) -> A:
        value = original(cls, identity)
        if isinstance(value, TargetVintage) and identity not in admitted:
            return replace(value, value=99.0)
        return value

    monkeypatch.setattr(case.repo, "get", perturb)
    result = case.engine.fit(case.fixture.learned_spec, case.fixture.training_ids, 40, 40, 40)
    assert canonical_json(result) == canonical_json(case.fixture.learned)


def test_native_in_sample_prediction_cannot_train_or_contribute(case: Case) -> None:
    from afre.mixture import ExpertKind
    from afre.statistical_models import ModelEngine, PredictionScope

    expert = next(
        e for e in case.fixture.fixed.expert_set.experts if e.kind is ExpertKind.AFRE_POINT
    )
    sample_id = case.fixture.learned.rows[0].sample_id
    prediction = ModelEngine(case.repo).predict_samples(
        expert.model_id,
        (sample_id,),
        PredictionScope.IN_SAMPLE,
        computed_ns=expert.available_ns,
    )[0]
    with pytest.raises(ContractError, match="historically admissible"):
        case.engine.bind(expert.fingerprint, prediction.fingerprint)


def test_fixed_gate_has_explicit_causal_availability(case: Case) -> None:
    future = replace(case.fixture.fixed, available_ns=case.sample.timestamp_ns + 1)
    case.engine.publish_gate(future)
    with pytest.raises(ContractError, match="unavailable"):
        case.engine.forecast(replace(case.forecast.request, gate_id=future.fingerprint))
    on_time = replace(case.fixture.fixed, available_ns=case.sample.timestamp_ns)
    case.engine.publish_gate(on_time)
    forecast = case.engine.forecast(replace(case.forecast.request, gate_id=on_time.fingerprint))
    assert forecast.available_ns >= on_time.available_ns
