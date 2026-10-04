"""Closed typed model choices and bounded matrix/forecast metadata validation."""

from dataclasses import replace
from typing import cast

import pytest

from afre.features import ValueType
from afre.schema import ContractError
from afre.statistical_models import (
    InterceptPolicy,
    ModelBounds,
    ModelFamily,
    PersistenceReference,
    SolverIdentity,
)
from tests.statistical_models.conftest import ModelCase


@pytest.mark.parametrize(
    "changes",
    (
        {"random_seed": -1},
        {"random_seed": 2**64},
        {"l1_penalty": -1.0},
        {"l2_penalty": -1.0},
        {"max_iterations": 0},
        {"tolerance": 0.0},
        {"tolerance": 1.0},
        {"condition_limit": 0.0},
        {"intercept": InterceptPolicy.WITHIN_ORIGIN},
        {"intercept": InterceptPolicy.NONE, "regularize_intercept": True},
        {"reference_value": 1.0},
        {"solver": SolverIdentity.COORDINATE_DESCENT},
        {"l1_penalty": 1.0},
        {"l2_penalty": 1.0},
    ),
)
def test_spec_rejections(model_case: ModelCase, changes: dict[str, object]) -> None:
    constructor = replace
    with pytest.raises(ContractError):
        constructor(model_case.spec(), **changes)


def test_typed_family_features_and_preprocessing(model_case: ModelCase) -> None:
    c = model_case
    with pytest.raises(ContractError, match="wrong contract type"):
        replace(c.spec(), family=cast(ModelFamily, "linear_regression"))
    with pytest.raises(ContractError, match="duplicate"):
        replace(c.spec(), preprocessing_state_ids=(c.preprocessing.fingerprint,) * 2)
    with pytest.raises(ContractError, match="numeric"):
        feature = c.fixture.definition.feature_set.definitions[0]
        from afre.feature_store import FeatureSetManifest

        replace(
            c.spec(),
            feature_set=FeatureSetManifest(
                (
                    replace(
                        feature,
                        definition=replace(feature.definition, value_type=ValueType.TEXT),
                    ),
                )
            ),
        )
    with pytest.raises(ContractError, match="persistence"):
        replace(
            c.spec(), family=ModelFamily.PERSISTENCE, solver=SolverIdentity.REFERENCE_STATISTIC
        )
    with pytest.raises(ContractError, match="residual"):
        replace(c.spec(), family=ModelFamily.RESIDUAL_LINEAR)
    with pytest.raises(ContractError, match="window"):
        PersistenceReference(
            c.fixture.definition.feature_set.definitions[0].definition.fingerprint,
            c.spec().target.fingerprint,
            0,
            "1",
        )
    with pytest.raises(ContractError, match="reference"):
        replace(
            c.spec(),
            family=ModelFamily.REFERENCE_VALUE,
            solver=SolverIdentity.REFERENCE_STATISTIC,
        )


@pytest.mark.parametrize(
    "changes",
    (
        {"samples": 0},
        {"features": 129},
        {"audit_depth": 65},
        {"serialized_bytes": 16 * 1024 * 1024 + 1},
    ),
)
def test_bounds_contract(changes: dict[str, int]) -> None:
    with pytest.raises(ContractError):
        ModelBounds(**changes)


def test_fit_clock_and_model_identity_changes(model_case: ModelCase) -> None:
    c = model_case
    spec = c.spec()
    for clocks in ((39, 40, 40), (40, 39, 40), (40, 41, 40)):
        with pytest.raises(ContractError):
            c.engine.fit_model(spec, *clocks)
    run = c.engine.fit_model(spec, 40, 40, 40)
    assert replace(spec, random_seed=1).fingerprint != spec.fingerprint
    assert replace(spec, tolerance=1e-8).fingerprint != spec.fingerprint
    with pytest.raises(ContractError, match="fit/availability"):
        replace(run.inputs, fit_started_ns=39)
