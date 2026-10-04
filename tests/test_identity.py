from dataclasses import replace
from typing import Any

import pytest

from afre.datasets import AdjustmentBasis, AdjustmentPolicy
from afre.features import FeatureSet, MissingPolicy
from afre.ids import InstrumentId, validate_digest, validate_fingerprint
from afre.lineage import Parameter
from afre.schema import ContractError, contract, ensure_artifact, enum, matches
from examples.foundation_demo import Demo


def test_dataset_identity_sensitivity(demo: Demo) -> None:
    dataset = demo.row.dataset
    different_feature = replace(dataset.feature_set.definitions[0], version="2")
    changes = (
        {"feature_set": FeatureSet((different_feature, dataset.feature_set.definitions[1]))},
        {"universe": replace(dataset.universe, selection_version="2")},
        {"targets": (replace(dataset.targets[0], implementation_version="2"),)},
        {"source_dataset_ids": (demo.instrument.fingerprint,)},
        {
            "adjustment": AdjustmentPolicy(
                AdjustmentBasis.TOTAL_RETURN, 0, dataset.source_dataset_ids[0]
            )
        },
        {"processing_version": "2"},
        {"engine_version": "0.1.1"},
    )
    for change in changes:
        assert replace(dataset, **change).fingerprint != dataset.fingerprint


def test_model_identity_sensitivity(demo: Demo) -> None:
    model = demo.experiment.model
    changes = (
        {"feature_set": FeatureSet((model.feature_set.definitions[0],))},
        {"target": replace(model.target, implementation_version="2")},
        {
            "target": replace(
                model.target,
                horizon=replace(
                    model.target.horizon,
                    duration_ns=2 * (model.target.horizon.duration_ns or 0),
                ),
            )
        },
        {"hyperparameters": (Parameter("intercept", False),)},
        {"random_seed": 43},
        {"training_policy": replace(model.training_policy, version="2")},
        {"implementation_version": "2"},
    )
    for change in changes:
        assert replace(model, **change).fingerprint != model.fingerprint


def test_order_independence_and_domain_separation(demo: Demo) -> None:
    dataset = demo.row.dataset
    assert FeatureSet(tuple(reversed(dataset.feature_set.definitions))) == dataset.feature_set
    params = (Parameter("b", 2), Parameter("a", 1))
    model = replace(demo.experiment.model, hyperparameters=params)
    assert (
        model.fingerprint == replace(model, hyperparameters=tuple(reversed(params))).fingerprint
    )
    assert (
        replace(demo.row, features=tuple(reversed(demo.features))).fingerprint
        == demo.row.fingerprint
    )
    source_ids = (*dataset.source_dataset_ids, demo.instrument.fingerprint)
    target2 = replace(dataset.targets[0], implementation_version="2")
    extended = replace(
        dataset, source_dataset_ids=source_ids, targets=(*dataset.targets, target2)
    )
    assert (
        replace(
            extended,
            source_dataset_ids=tuple(reversed(source_ids)),
            targets=tuple(reversed(extended.targets)),
        ).fingerprint
        == extended.fingerprint
    )
    assert Parameter("x", 1).fingerprint != Parameter("x", 1.0).fingerprint
    assert Parameter("x", -0.0).fingerprint == Parameter("x", 0.0).fingerprint
    assert demo.experiment.fingerprint.startswith("afre.experiment_spec:1.0:")
    assert demo.experiment.model.fingerprint.startswith("afre.model_spec:1.0:")
    assert replace(demo.experiment, code_version="2").fingerprint != demo.experiment.fingerprint


@pytest.mark.parametrize(
    "changes",
    [
        {"targets": ()},
        {"source_dataset_ids": ()},
        {"source_dataset_ids": ("bad",)},
        {"source_dataset_ids": ("bad", "bad")},
        {"adjustment": AdjustmentPolicy(AdjustmentBasis.RAW, 1)},
        {"missing_policy": MissingPolicy.REJECT},
    ],
)
def test_invalid_dataset(demo: Demo, changes: dict[str, Any]) -> None:
    with pytest.raises(ContractError):
        replace(demo.row.dataset, **changes)


def test_adjustment_policy_and_calendar(demo: Demo) -> None:
    source = demo.row.dataset.source_dataset_ids[0]
    for basis in AdjustmentBasis:
        policy = AdjustmentPolicy(basis, 0, None if basis is AdjustmentBasis.RAW else source)
        assert replace(demo.row.dataset, adjustment=policy).adjustment == policy
    with pytest.raises(ContractError):
        AdjustmentPolicy(AdjustmentBasis.RAW, 0, source)
    with pytest.raises(ContractError):
        AdjustmentPolicy(AdjustmentBasis.SPLIT_ADJUSTED, 0)
    with pytest.raises(ContractError):
        replace(
            demo.row.dataset,
            adjustment=AdjustmentPolicy(
                AdjustmentBasis.TOTAL_RETURN, 0, demo.instrument.fingerprint
            ),
        )
    from afre.horizons import ForecastHorizon, HorizonBasis

    session_target = replace(
        demo.target.target,
        horizon=ForecastHorizon(
            HorizonBasis.TRADING_SESSIONS, count=1, calendar_id="synthetic-calendar-v1"
        ),
    )
    assert replace(demo.row.dataset, targets=(session_target,)).targets == (session_target,)
    with pytest.raises(ContractError):
        replace(
            demo.row.dataset,
            targets=(
                replace(
                    session_target, horizon=replace(session_target.horizon, calendar_id="other")
                ),
            ),
        )
    rejecting_features = FeatureSet(
        tuple(
            replace(item, missing_policy=MissingPolicy.REJECT)
            for item in demo.row.dataset.feature_set.definitions
        )
    )
    replace(
        demo.row.dataset, feature_set=rejecting_features, missing_policy=MissingPolicy.REJECT
    )


def test_duplicate_contracts_and_references(demo: Demo) -> None:
    feature = demo.features[0].definition
    for definitions in ((), (feature, feature), (feature, replace(feature, unit="other"))):
        with pytest.raises(ContractError):
            FeatureSet(definitions)
    with pytest.raises(ContractError):
        replace(demo.experiment.model, hyperparameters=(Parameter("x", 1), Parameter("x", 2)))
    with pytest.raises(ContractError):
        contract("instrument")(InstrumentId)
    with pytest.raises(ContractError):
        enum(AdjustmentBasis)
    with pytest.raises(ContractError):
        ensure_artifact(object())
    with pytest.raises(ContractError):
        validate_fingerprint(demo.target.fingerprint, "feature_value")


@pytest.mark.parametrize(
    "identity",
    ["", "a" * 64, "afre.target_row:2.0:" + "a" * 64, "afre.target_row:1.0:" + "A" * 64],
)
def test_invalid_fingerprint(identity: str) -> None:
    with pytest.raises(ContractError):
        validate_fingerprint(identity)


@pytest.mark.parametrize("value", ["a" * 63, "A" * 64, "x" * 64])
def test_invalid_digest(value: str) -> None:
    with pytest.raises(ContractError):
        validate_digest(value)


@pytest.mark.parametrize(
    "namespace,value",
    [("ticker?", "X"), ("security", "a/b"), ("", "x"), ("security", "x" * 129)],
)
def test_invalid_security_identity(namespace: str, value: str) -> None:
    with pytest.raises(ContractError):
        InstrumentId(namespace, value)


def test_strict_tuple_schema() -> None:
    assert matches((1, "x"), tuple[int, str])
    assert not matches((1,), tuple[int, str])
    assert not matches([1], tuple[int, ...])
    assert not matches((True,), tuple[int, ...])
    assert not matches(1, "untrusted annotation")
