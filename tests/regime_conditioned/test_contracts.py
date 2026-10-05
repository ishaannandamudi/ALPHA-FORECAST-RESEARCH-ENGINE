"""Reject ambiguous state identity, unnormalized vectors and incompatible contracts."""

from dataclasses import FrozenInstanceError, replace

import pytest

from afre.ids import InstrumentId
from afre.regime_conditioned import (
    RegimeBounds,
    RegimeFallback,
    RegimeMembership,
    RegimeMembershipKind,
    RegimeModelFamily,
    RegimeScope,
    RegimeSubject,
)
from afre.schema import ContractError
from afre.serialization import canonical_json, deserialize
from examples.regime_conditioned_demo import taxonomy
from tests.regime_conditioned.conftest import Case
from tests.regime_conditioned.test_models import changed


@pytest.mark.parametrize(
    "values",
    [
        (0.2, 0.2),
        (-0.1, 1.1),
        (float("nan"), 0.0),
        (float("inf"), 0.0),
        (1.0,),
        (0.4, 0.4, 0.2),
    ],
)
def test_invalid_soft_vectors(values: tuple[float, ...]) -> None:
    with pytest.raises((ContractError, ValueError)):
        RegimeMembership(
            RegimeMembershipKind.SOFT,
            ("A", "B"),
            probabilities=tuple(zip(("A", "B"), values, strict=True)),
        )


@pytest.mark.parametrize(
    "probabilities",
    [(("B", 0.3), ("A", 0.7)), (("A", 0.7), ("A", 0.3)), (("A", 0.7), ("C", 0.3))],
)
def test_order_duplicates_unknown(probabilities: tuple[tuple[str, float], ...]) -> None:
    with pytest.raises(ContractError):
        RegimeMembership(RegimeMembershipKind.SOFT, ("A", "B"), probabilities=probabilities)


@pytest.mark.parametrize(
    "changes",
    [
        {"hard_state": "C"},
        {"probabilities": (("A", 1.0), ("B", 0.0))},
        {"states": ("A", "A")},
        {"tolerance": 0.0},
        {"tolerance": 0.1},
        {"normalization_policy": "normalize"},
    ],
)
def test_hard_policy_rejections(changes: dict[str, object]) -> None:
    with pytest.raises(ContractError):
        changed(RegimeMembership(RegimeMembershipKind.HARD, ("A", "B"), "A"), **changes)


def test_soft_exact_preservation_and_identity() -> None:
    values = (("B", 0.3), ("A", 0.7))
    m = RegimeMembership(RegimeMembershipKind.SOFT, ("B", "A"), probabilities=values)
    assert m.probabilities == values and m.weights == (0.3, 0.7)
    assert deserialize(canonical_json(m)) == m
    with pytest.raises(FrozenInstanceError):
        m.tolerance = 1e-10  # type: ignore[misc]


@pytest.mark.parametrize(
    "field,value",
    [
        ("states", ("A", "A")),
        ("labels", ("one",)),
        ("dimensionality", 3),
        ("implementation_version", "future"),
    ],
)
def test_taxonomy_rejections(field: str, value: object) -> None:
    with pytest.raises(ContractError):
        changed(taxonomy(), **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("minimum_samples", 1),
        ("minimum_state_samples", 1),
        ("minimum_effective_support", 0.5),
        ("minimum_evaluation_group", 1),
        ("seed", -1),
        ("low_confidence_threshold", 1.1),
        ("fitting_policy", "hidden"),
        ("weighting_policy", "argmax"),
        ("calibration_policy", "reuse-global"),
        ("implementation_version", "future"),
        ("allowed_memberships", ()),
        ("allowed_memberships", (RegimeMembershipKind.SOFT,)),
    ],
)
def test_spec_rejections(case: Case, field: str, value: object) -> None:
    with pytest.raises(ContractError):
        changed(case.hard.spec, **{field: value})


@pytest.mark.parametrize(
    "scope", [RegimeScope.SECURITY, RegimeScope.SECTOR, RegimeScope.MARKET]
)
def test_subject_requires_evidence(scope: RegimeScope) -> None:
    with pytest.raises(ContractError):
        RegimeSubject(scope, InstrumentId("regime", "entity"))


@pytest.mark.parametrize(
    "field,value",
    [
        ("states", 0),
        ("states", 4097),
        ("taxonomies", 0),
        ("snapshots", 0),
        ("samples", 1_000_001),
        ("transitions", 0),
        ("evaluations", 0),
        ("drift_windows", 0),
        ("audit_depth", 65),
        ("serialized_bytes", 16 * 1024 * 1024 + 1),
    ],
)
def test_bounds_contract(field: str, value: int) -> None:
    with pytest.raises(ContractError):
        replace(RegimeBounds(), **{field: value})


def test_schema_roundtrip_and_policy_identities(case: Case) -> None:
    for f in (case.hard, case.soft):
        for value in (f.spec, f.model, case.repo.get_any(f.forecast_ids[0])):
            assert value.schema_version == "1.0" and deserialize(canonical_json(value)) == value
    assert (
        replace(case.hard.spec, fallback=RegimeFallback.FAIL).fingerprint
        != case.hard.spec.fingerprint
    )
    with pytest.raises(ContractError, match="event composition"):
        replace(
            case.hard.spec,
            event_model_id="afre.ec_model:1.0:" + "0" * 64,
            family=RegimeModelFamily.REGIME_RESIDUAL_OFFSET,
        )
