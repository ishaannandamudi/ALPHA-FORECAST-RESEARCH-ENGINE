"""Explicit output/identity/missingness contracts reject ambiguous expert composition."""

from dataclasses import FrozenInstanceError, replace

import pytest

from afre.mixture import (
    ExpertKind,
    ExpertMissingPolicy,
    ExpertOutput,
    ExpertQuality,
    ExpertSet,
    FixedGateSpec,
    GatingFeatureReference,
    MixtureBounds,
)
from afre.schema import ContractError
from afre.serialization import canonical_json, deserialize
from examples.mixture_demo import external_reference
from tests.mixture.conftest import Case


@pytest.mark.parametrize(
    "weights",
    [(-0.1, 1.1), (0.0, 0.0), (0.4, 0.5), (1.0, 1.0), (float("nan"), 0.5), (float("inf"), 0.5)],
)
def test_fixed_invalid_weight_vectors(case: Case, weights: tuple[float, float]) -> None:
    experts = case.fixture.learned_spec.expert_set
    with pytest.raises(ContractError):
        FixedGateSpec(experts, tuple(zip(experts.expert_ids, weights, strict=True)))


@pytest.mark.parametrize(
    "field,value",
    [
        ("tolerance", 1e-3),
        ("normalization_policy", "normalize"),
        ("implementation_version", "unrecognized"),
    ],
)
def test_fixed_numerical_policies(case: Case, field: str, value: object) -> None:
    with pytest.raises(ContractError):
        replace(case.fixture.fixed, **{field: value})  # type: ignore[arg-type]


def test_duplicate_semantic_expert_and_weight_ids(case: Case) -> None:
    e = case.fixture.learned_spec.expert_set.experts[0]
    with pytest.raises(ContractError, match="duplicate semantic"):
        ExpertSet((e, replace(e, expert_id="alias")), e.target)
    with pytest.raises(ContractError, match="duplicate"):
        ExpertSet((e, e), e.target)
    with pytest.raises(ContractError, match="ordered"):
        replace(case.fixture.fixed, weights=((e.fingerprint, 0.5), (e.fingerprint, 0.5)))


def test_target_and_horizon_identity_are_exact(case: Case) -> None:
    e = case.fixture.learned_spec.expert_set.experts[0]
    changed = replace(
        e.target,
        horizon=replace(e.target.horizon, duration_ns=(e.target.horizon.duration_ns or 1) + 1),
    )
    other = external_reference(changed, ExpertKind.EXTERNAL_GENERIC, "other-horizon")
    with pytest.raises(ContractError, match="target/horizon"):
        ExpertSet((e, other), e.target)
    with pytest.raises(ContractError, match="target/horizon"):
        ExpertSet((e,), changed)


@pytest.mark.parametrize(
    "output", [ExpertOutput.PROBABILISTIC, ExpertOutput.CALIBRATED_PROBABILISTIC]
)
def test_incompatible_output_semantics(case: Case, output: ExpertOutput) -> None:
    e = case.fixture.learned_spec.expert_set.experts[0]
    with pytest.raises(ContractError):
        probabilistic = replace(e, expert_id="different-output", output=output)
        ExpertSet((e, probabilistic), e.target)


def test_native_kind_output_contract(case: Case) -> None:
    native = next(
        e for e in case.fixture.fixed.expert_set.experts if e.kind is ExpertKind.AFRE_POINT
    )
    with pytest.raises(ContractError, match="point expert output"):
        replace(native, output=ExpertOutput.PROBABILISTIC)


@pytest.mark.parametrize(
    "policy", [ExpertMissingPolicy.FAIL, ExpertMissingPolicy.DROP_AND_RENORMALIZE]
)
def test_fallback_identity_cannot_be_hidden(case: Case, policy: ExpertMissingPolicy) -> None:
    experts = case.fixture.learned_spec.expert_set
    with pytest.raises(ContractError, match="fallback"):
        replace(experts, missing_policy=policy, fallback_id=experts.expert_ids[0])
    with pytest.raises(ContractError, match="fallback"):
        replace(experts, missing_policy=ExpertMissingPolicy.USE_DECLARED_FALLBACK)


@pytest.mark.parametrize("field", ["experts", "atoms", "audit_depth", "serialized_bytes"])
def test_resource_contract_requires_positive_limits(field: str) -> None:
    with pytest.raises(ContractError):
        replace(MixtureBounds(), **{field: 0})


@pytest.mark.parametrize(
    "field,value",
    [
        ("experts", 257),
        ("components", 257),
        ("audit_depth", 65),
        ("serialized_bytes", 17 * 1024 * 1024),
    ],
)
def test_hard_resource_ceiling(field: str, value: int) -> None:
    with pytest.raises(ContractError):
        replace(MixtureBounds(), **{field: value})


def test_canonical_safe_bytes_and_immutability(case: Case) -> None:
    f = case.forecast
    assert deserialize(canonical_json(f)) == f
    assert deserialize(canonical_json(case.fixture.learned)) == case.fixture.learned
    assert (
        replace(
            case.fixture.fixed,
            expert_set=replace(
                case.fixture.fixed.expert_set,
                experts=tuple(reversed(case.fixture.fixed.expert_set.experts)),
            ),
            weights=tuple(reversed(case.fixture.fixed.weights)),
        )
        == case.fixture.fixed
    )
    with pytest.raises(FrozenInstanceError):
        f.value = 9.0  # type: ignore[misc]


def test_gating_targets_and_execution_are_not_supported_sources(case: Case) -> None:
    assert case.sample.origin is not None and case.sample.target_id
    with pytest.raises(ContractError, match="gating source"):
        GatingFeatureReference(
            "future-target", case.sample.target_id, case.sample.origin, 0, 1.0
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("objective", "validation-search"),
        ("feature_policy", "neural"),
        ("normalization_policy", "hidden"),
        ("intercept_policy", "free"),
        ("maximum_iterations", 0),
        ("convergence_tolerance", 0.0),
        ("minimum_samples", 0),
        ("ridge_penalty", -0.1),
    ],
)
def test_learned_policy_is_closed(case: Case, field: str, value: object) -> None:
    with pytest.raises(ContractError):
        replace(case.fixture.learned_spec, **{field: value})  # type: ignore[arg-type]


def test_neutral_provider_names_remain_data(case: Case) -> None:
    expert = external_reference(
        case.fixture.fixed.expert_set.target,
        ExpertKind.EXTERNAL_OPTIONS,
        "unusual-provider-name",
    )
    assert case.engine.register_expert(expert) == expert.fingerprint
    assert expert.quality is ExpertQuality.VALID
