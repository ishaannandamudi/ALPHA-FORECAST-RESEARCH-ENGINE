"""Train-only fitting, missing observations, zero scales and held-out outliers."""

import json
from dataclasses import replace

import pytest

from afre.feature_store.normalization import NormalizationMethod
from afre.research_datasets import FoldPreprocessingSpec, Partition, ZeroScaleRule, apply_state
from afre.research_datasets.preprocessing import fit_parameters
from afre.schema import ContractError
from examples.feature_store_demo import clocks, source_vintage
from examples.research_dataset_demo import split_definition
from examples.universe_demo import SECURITIES
from tests.research_datasets.conftest import Case


@pytest.mark.parametrize(
    "method", [m for m in NormalizationMethod if m is not NormalizationMethod.RANK]
)
def test_train_only_simple_statistics(case: Case, method: NormalizationMethod) -> None:
    spec = replace(
        case.fixture.preprocessing,
        normalization=replace(case.fixture.preprocessing.normalization, method=method),
    )
    with case.repository.transaction():
        case.repository.put(spec)
    definition = replace(
        split_definition(case.fixture), preprocessing_spec_ids=(spec.fingerprint,)
    )
    split = case.engine.build_split(case.dataset.fingerprint, definition)
    fold = case.engine.folds(split.fingerprint)[0]
    state = case.engine.fit_preprocessing(fold.fingerprint, spec)
    assert state.normalization.available_ns == fold.training_cutoff_ns
    train_ids = {s.fingerprint for s in case.engine.training_samples_for_fold(fold.fingerprint)}
    assert set(state.fit_sample_ids) <= train_ids
    heldout_ids = {
        s.fingerprint
        for p in (Partition.VALIDATION, Partition.TEST)
        for s in case.engine.partition_samples(fold.fingerprint, p)
    }
    assert not heldout_ids & set(state.fit_sample_ids)
    # Five representative origin/security observations, regardless of two target horizons.
    assert len(state.fit_sample_ids) == 5 and len(state.skipped_sample_ids) == 1
    params = {p.name: p.value for p in state.normalization.parameters}
    if method is NormalizationMethod.STANDARDIZE:
        assert params["mean"] == 17.0
    assert apply_state(state, None, 40) is None
    assert apply_state(state, 10.0, 40) is not None
    with pytest.raises(ContractError, match="before availability"):
        apply_state(state, 10.0, 39)
    with pytest.raises(ContractError, match="input availability"):
        case.engine.export_rows(case.dataset.fingerprint, 100, state, 40)
    exported = json.loads(case.engine.export_rows(case.dataset.fingerprint, 100, state, 100))
    assert any(
        cell["data"].get("preprocessing_state_id") == state.fingerprint
        for row in exported["rows"]
        for cell in row["cells"].values()
        if cell["role"] == "feature"
    )
    case.engine.audit_fold(fold.fingerprint)
    case.repository.audit()


def test_validation_and_test_outlier_cannot_change_fit(case: Case) -> None:
    split = case.engine.build_split(case.dataset.fingerprint, split_definition(case.fixture))
    first = case.engine.folds(split.fingerprint)[0]
    fitted = case.engine.fit_preprocessing(first.fingerprint, case.fixture.preprocessing)
    old_audit = case.engine.audit_fold(first.fingerprint)
    feature = case.fixture.preprocessing.normalization.feature
    with case.repository.transaction():
        for at in (40, 70):
            old = source_vintage(feature, at, at, 1000.0, entity=SECURITIES[0].instrument)
            case.repository.put(
                replace(old, value=1000000.0, predecessor_id=old.fingerprint, clocks=clocks(at))
            )
    dataset = case.engine.build_dataset(
        case.fixture.definition, case.fixture.requests, 100, 100
    )
    revised_split = case.engine.build_split(dataset.fingerprint, split_definition(case.fixture))
    revised = case.engine.fit_preprocessing(
        revised_split.fold_ids[0], case.fixture.preprocessing
    )
    assert revised.normalization.parameters == fitted.normalization.parameters
    assert revised.normalization.fit_sample_ids == fitted.normalization.fit_sample_ids
    # A later additional fit must not mutate a previously frozen contamination audit.
    case.engine.fit_preprocessing(first.fingerprint, case.fixture.preprocessing, 41)
    assert case.repository.get(type(old_audit), old_audit.fingerprint) == old_audit
    case.repository.audit()


@pytest.mark.parametrize(
    "method",
    [
        NormalizationMethod.STANDARDIZE,
        NormalizationMethod.ROBUST_STANDARDIZE,
        NormalizationMethod.MINMAX,
    ],
)
def test_zero_scale_policy(method: NormalizationMethod, case: Case) -> None:
    normalization = replace(case.fixture.preprocessing.normalization, method=method)
    spec = FoldPreprocessingSpec(normalization)
    with pytest.raises(ContractError, match="zero"):
        fit_parameters(spec, (4.0, 4.0))
    assert fit_parameters(replace(spec, zero_scale=ZeroScaleRule.UNIT_SCALE), (4.0, 4.0))


def test_fit_and_export_reject_wrong_boundary(case: Case) -> None:
    split = case.engine.build_split(case.dataset.fingerprint, split_definition(case.fixture))
    with pytest.raises(ContractError, match="availability"):
        case.engine.fit_preprocessing(split.fold_ids[0], case.fixture.preprocessing, 39)
    state = case.engine.fit_preprocessing(split.fold_ids[0], case.fixture.preprocessing)
    with pytest.raises(ContractError, match="application"):
        case.engine.export_rows(case.dataset.fingerprint, 100, state)
    with case.repository.transaction(), pytest.raises(ContractError, match="statistics"):
        case.repository.put(replace(state, fit_sample_ids=(case.dataset.sample_ids[-1],)))


def test_within_origin_and_group_contracts_are_prepared_and_not_fit(case: Case) -> None:
    from afre.research_datasets import PreprocessingScope, PurgeScope

    split = case.engine.build_split(case.dataset.fingerprint, split_definition(case.fixture))
    for scope, group in (
        (PreprocessingScope.WITHIN_ORIGIN, None),
        (PreprocessingScope.WITHIN_ORIGIN_GROUP, PurgeScope.SECTOR),
    ):
        spec = replace(case.fixture.preprocessing, scope=scope, group_scope=group)
        with pytest.raises(ContractError, match="deferred"):
            case.engine.fit_preprocessing(split.fold_ids[0], spec)
        with pytest.raises(ContractError, match="deferred"):
            fit_parameters(spec, (1.0, 2.0))
    with pytest.raises(ContractError, match="group scope"):
        replace(case.fixture.preprocessing, scope=PreprocessingScope.WITHIN_ORIGIN_GROUP)
