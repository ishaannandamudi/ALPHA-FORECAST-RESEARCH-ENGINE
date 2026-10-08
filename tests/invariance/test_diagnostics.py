"""Native parameter, prediction, rank, distribution and audit research paths."""

from dataclasses import replace

import pytest

from afre.invariance import (
    ComparabilityStatus,
    EnvironmentMembership,
    SampleIntersectionPolicy,
    StabilityMetricName,
)
from afre.invariance.coefficients import raw_coefficients
from afre.invariance.forecasts import forecast_source
from afre.nonlinear.artifacts import NonlinearForecast
from afre.orthogonalization import OrthogonalizationEngine, SignalObservation
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from afre.sequence.artifacts import SequenceForecast
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from examples.invariance_fixture import native_forecasts
from tests.invariance.conftest import Case


@pytest.mark.parametrize(
    "family",
    ["linear", "tree", "nonlinear", "sequence", "projection", "redundancy", "uncertainty"],
)
def test_supplied_native_parameters(case: Case, family: str) -> None:
    f = case.fixture
    envs = (
        f.environment_set.definitions[0].fingerprint,
        f.environment_set.definitions[1].fingerprint,
    )
    if family == "linear":
        identity = f.upstream.upstream.covariances[0].model_id
    elif family in ("tree", "nonlinear", "sequence"):
        source = case.repo.get_any(f.upstream.upstream.ids(family)[0])
        assert isinstance(source, (NonlinearForecast, SequenceForecast))
        identity = source.model_id
    elif family == "projection":
        identity = f.upstream.projection.fingerprint
    elif family == "redundancy":
        identity = (
            OrthogonalizationEngine(case.repo)
            .evaluate(
                f.upstream.residual_ids(Partition.VALIDATION), 100, 100, target_diagnostics=True
            )
            .fingerprint
        )
    else:
        identity = f.upstream.upstream.results("mixture")[0]
    before = canonical_json(case.repo.get_any(identity))
    diagnostic = case.engine.models(
        f.spec.fingerprint,
        tuple((e, identity) for e in envs),
        100,
        100,
        raw_scale=family in ("linear", "projection"),
    )
    assert diagnostic.status is ComparabilityStatus.PARTIALLY_COMPARABLE
    assert diagnostic.summaries and all(s.minimum == s.maximum for s in diagnostic.summaries)
    assert canonical_json(case.repo.get_any(identity)) == before
    if family == "tree":
        assert any(s.name.startswith("split-count:") for s in diagnostic.summaries)
        assert any(s.name.startswith("leaf-support:") for s in diagnostic.summaries)
    if family == "sequence":
        assert any(s.name == "readout-L1-state-sensitivity" for s in diagnostic.summaries)
    if family == "uncertainty":
        assert any(s.name.startswith("exact-component-share:") for s in diagnostic.summaries)
    audit = case.engine.audit(diagnostic.fingerprint)
    assert identity in audit.node_ids and any("causal" in t for t in audit.declarations)


def test_raw_linear_preserves_fitted_predictions(case: Case) -> None:
    f = case.fixture
    model = case.repo.get(FittedModelArtifact, f.upstream.upstream.covariances[0].model_id)
    converted = raw_coefficients(case.repo, model)
    assert converted is not None
    # Existing unstandardized synthetic fit must remain exactly represented.
    assert converted == (model.intercept, model.coefficients)


@pytest.mark.parametrize("policy", list(SampleIntersectionPolicy))
def test_feature_shift_exact_native_observations(
    case: Case, policy: SampleIntersectionPolicy
) -> None:
    f = case.fixture
    spec = case.engine.register(replace(f.spec, intersection=policy))
    envs = (
        f.environment_set.definitions[0].fingerprint,
        f.environment_set.definitions[1].fingerprint,
    )
    reference = f.upstream.spec.candidate.fingerprint
    obs = tuple(
        i
        for row in f.upstream.partition(Partition.VALIDATION)
        for i in row.observation_ids
        if case.repo.get(SignalObservation, i).reference_id == reference
    )
    shift = case.engine.shift(
        spec.fingerprint, reference, envs, f.membership_ids, obs, 100, 100
    )
    assert shift.mean_shift == pytest.approx((shift.right.mean or 0) - (shift.left.mean or 0))
    if policy is not SampleIntersectionPolicy.PER_ENVIRONMENT_NATIVE:
        assert shift.left.sample_ids == shift.right.sample_ids and shift.ks_distance == 0
    else:
        assert len(shift.left.sample_ids) == len(shift.right.sample_ids) == 8
    assert shift.missing_fraction_shift == 0
    assert case.engine.audit(shift.fingerprint).root_id == shift.fingerprint


def test_prediction_and_PIT_rank_comparison(case: Case) -> None:
    f = case.fixture
    # Native probability and point share the same underlying supplied model and target.
    one_time = tuple(
        i for i in f.spec.sample_ids if case.repo.get(ResearchSample, i).timestamp_ns == 60
    )
    left_ids = tuple(
        i for i in f.spec.forecast_ids if forecast_source(case.repo, i).sample_id in one_time
    )
    right_ids = tuple(
        i
        for i in native_forecasts(case.repo, f.upstream, False)
        if forecast_source(case.repo, i).sample_id in one_time
    )
    a = case.engine.register(replace(f.spec, sample_ids=one_time, forecast_ids=left_ids))
    b = case.engine.register(replace(a, forecast_ids=right_ids))
    env = f.environment_set.definitions[0].fingerprint
    members = tuple(
        i
        for i in f.membership_ids
        if case.repo.get(EnvironmentMembership, i).environment_id == env
        and case.repo.get(EnvironmentMembership, i).sample_id in one_time
    )
    d = case.engine.predictions(a.fingerprint, b.fingerprint, env, members, 100, 100)
    assert d.top_k_overlap == 1 and d.mean_rank_displacement == 0
    assert d.pearson == pytest.approx(1) and d.spearman == 1
    assert d.mean_absolute_difference == 0 and d.sign_agreement == 1


def test_source_and_model_bytes_never_mutated(case: Case) -> None:
    f = case.fixture
    tables = tuple(
        row[0]
        for row in case.repo._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'inv_%' ORDER BY name"
        )
    )
    before = {
        table: case.repo._connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        for table in tables
    }
    ms = case.engine.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
    case.engine.compare(ms[0].fingerprint, ms[1].fingerprint, 100)
    case.engine.trend(
        tuple(m.fingerprint for m in ms if m.name is StabilityMetricName.MAE), 100
    )
    assert before == {
        table: case.repo._connection.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
        for table in tables
    }
    assert not any(
        hasattr(case.engine, name)
        for name in (
            "fit",
            "refit",
            "prune",
            "promote",
            "select_model",
            "replace_model",
            "calibrate",
        )
    )


def test_incompatible_model_families_explicit(case: Case) -> None:
    f = case.fixture
    envs = (
        f.environment_set.definitions[0].fingerprint,
        f.environment_set.definitions[1].fingerprint,
    )
    a = f.upstream.upstream.covariances[0].model_id
    b = f.upstream.projection.fingerprint
    d = case.engine.models(f.spec.fingerprint, ((envs[0], a), (envs[1], b)), 100, 100)
    assert d.status is ComparabilityStatus.INCOMPARABLE and not d.summaries
    with pytest.raises(ContractError):
        case.engine.models(f.spec.fingerprint, ((envs[0], a), (envs[1], b)), 39, 100)


def test_missing_feature_fraction_shift_preserved(case: Case) -> None:
    f = case.fixture
    left = f.spec.baseline_environment_id
    assert left is not None
    right = next(d.fingerprint for d in f.environment_set.definitions if d.fingerprint != left)
    reference = f.upstream.spec.candidate.fingerprint
    obs = tuple(
        case.repo.get(SignalObservation, i)
        for row in f.upstream.partition(Partition.VALIDATION)
        for i in row.observation_ids
        if case.repo.get(SignalObservation, i).reference_id == reference
    )
    remove = next(o for o in obs if o.origin.timestamp_ns == 40)
    ids = tuple(o.fingerprint for o in obs if o != remove)
    shift = case.engine.shift(
        f.spec.fingerprint, reference, (left, right), f.membership_ids, ids, 100, 100
    )
    assert shift.left.missing_fraction == 0.125 and shift.right.missing_fraction == 0.0
    assert shift.missing_fraction_shift == -0.125
    assert any(v is None for _, v in shift.left.values)


def test_standardized_native_fit_raw_affine_equivalence(case: Case) -> None:
    from afre.feature_store.normalization import NormalizationMethod, NormalizationSpec
    from afre.research_datasets import DatasetEngine
    from afre.research_datasets.preprocessing import FoldPreprocessingSpec
    from afre.research_datasets.splits import FoldDefinition, SplitDefinition
    from afre.statistical_models import ModelEngine
    from afre.statistical_models.artifacts import DesignMatrix, ModelFitInputs
    from afre.statistical_models.definitions import BaselineModelSpec

    model = case.repo.get(
        FittedModelArtifact, case.fixture.upstream.upstream.covariances[0].model_id
    )
    spec = case.repo.get(BaselineModelSpec, model.spec_id)
    preprocessing = tuple(
        FoldPreprocessingSpec(
            NormalizationSpec(feature, NormalizationMethod.STANDARDIZE, "test-standardize-v1")
        )
        for feature in spec.feature_set.definitions
    )
    fold = case.repo.get(FoldDefinition, spec.fold_id)
    definition = case.repo.get(SplitDefinition, fold.split_definition_id)
    with case.repo.transaction():
        for p in preprocessing:
            case.repo.put(p)
    dataset_engine = DatasetEngine(case.repo)
    split = dataset_engine.build_split(
        fold.dataset_id,
        replace(
            definition,
            name="split.standardized_stability_fixture",
            preprocessing_spec_ids=tuple(p.fingerprint for p in preprocessing),
        ),
    )
    states = tuple(
        dataset_engine.fit_preprocessing(split.fold_ids[0], p, 40) for p in preprocessing
    )
    supplied = ModelEngine(case.repo).fit_model(
        replace(
            spec,
            fold_id=split.fold_ids[0],
            preprocessing_state_ids=tuple(s.fingerprint for s in states),
        ),
        40,
        40,
        40,
    )
    fitted = case.repo.get(FittedModelArtifact, supplied.artifact_id)
    converted = raw_coefficients(case.repo, fitted)
    assert converted is not None
    intercept, betas = converted
    centers = {
        s.spec.normalization.feature.definition.fingerprint: dict(
            (p.name, float(p.value)) for p in s.normalization.parameters
        )
        for s in states
    }
    data = case.repo.get(
        DesignMatrix, case.repo.get(ModelFitInputs, fitted.fit_inputs_id).matrix_id
    )
    for row in data.rows:
        raw = tuple(
            x * centers[f]["stddev"] + centers[f]["mean"]
            for f, x in zip(fitted.feature_ids, row.values, strict=True)
        )
        expected = fitted.intercept + sum(
            b * x for b, x in zip(fitted.coefficients, row.values, strict=True)
        )
        assert intercept + sum(b * x for b, x in zip(betas, raw, strict=True)) == pytest.approx(
            expected, abs=1e-13
        )
