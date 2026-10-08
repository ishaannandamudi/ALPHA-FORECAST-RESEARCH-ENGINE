"""Independent ranks/calibration and final resource/availability boundary regressions."""

import ast
import math
from dataclasses import replace
from pathlib import Path

import pytest

from afre.invariance import (
    ComparabilityStatus,
    EnvironmentDefinition,
    EnvironmentKind,
    EnvironmentRule,
    EnvironmentSet,
    InvarianceBounds,
    InvarianceEngine,
    InvarianceRepository,
    SampleIntersectionPolicy,
    StabilityMetricName,
    StabilityTimeWindow,
)
from afre.invariance.forecasts import forecast_source
from afre.orthogonalization import SignalObservation
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from afre.statistical_models import ModelEngine, ModelFamily, PredictionScope
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.definitions import BaselineModelSpec
from afre.target_engine.models import TargetVintage
from tests.invariance.conftest import Case


@pytest.mark.parametrize("window_minimum", (False, True))
def test_feature_and_prediction_environment_minimums(case: Case, window_minimum: bool) -> None:
    f = case.fixture
    definitions = []
    for d in f.environment_set.definitions:
        assert d.window is not None
        definitions.append(
            replace(d, window=replace(d.window, minimum_count=20))
            if window_minimum
            else replace(d, minimum_count=20)
        )
    envset = case.engine.declare(EnvironmentSet(tuple(definitions), 40))
    spec = case.engine.register(
        replace(f.spec, environment_set_id=envset.fingerprint, baseline_environment_id=None)
    )
    members = tuple(
        case.engine.bind(d.fingerprint, i, constructed_ns=100)
        for d in envset.definitions
        for i in spec.sample_ids
    )
    reference = f.upstream.spec.candidate.fingerprint
    obs = tuple(
        i
        for row in f.upstream.partition(Partition.VALIDATION)
        for i in row.observation_ids
        if case.repo.get(SignalObservation, i).reference_id == reference
    )
    shift = case.engine.shift(
        spec.fingerprint,
        reference,
        (envset.definitions[0].fingerprint, envset.definitions[1].fingerprint),
        tuple(m.fingerprint for m in members),
        obs,
        100,
        100,
    )
    prediction = case.engine.predictions(
        spec.fingerprint,
        spec.fingerprint,
        envset.definitions[0].fingerprint,
        tuple(
            m.fingerprint
            for m in members
            if m.environment_id == envset.definitions[0].fingerprint
        ),
        100,
        100,
    )
    assert shift.status is prediction.status is ComparabilityStatus.INSUFFICIENT_DATA
    assert shift.ks_distance is prediction.pearson is None


@pytest.mark.parametrize("calibrated_left", (False, True))
def test_cross_model_calibration_class_mismatch_explicit(
    case: Case, calibrated_left: bool
) -> None:
    f = case.fixture
    cal_ids = f.upstream.upstream.ids("calibrated")
    ids = tuple(sorted(forecast_source(case.repo, i).sample_id for i in cal_ids))
    calibrated = case.engine.register(replace(f.spec, sample_ids=ids, forecast_ids=cal_ids))
    probability = case.engine.register(
        replace(
            calibrated,
            forecast_ids=tuple(
                i for i in f.spec.forecast_ids if forecast_source(case.repo, i).sample_id in ids
            ),
        )
    )
    members = tuple(
        case.engine.bind(d.fingerprint, i, constructed_ns=100).fingerprint
        for d in f.environment_set.definitions
        for i in ids
    )
    metrics = tuple(
        next(
            m
            for m in case.engine.evaluate(s.fingerprint, members, 100, 100)
            if m.name is StabilityMetricName.MAE
        )
        for s in (calibrated, probability)
    )
    left, right = metrics if calibrated_left else tuple(reversed(metrics))
    comparison = case.engine.compare(left.fingerprint, right.fingerprint, 100, cross_model=True)
    assert comparison.status is ComparabilityStatus.INCOMPARABLE
    assert comparison.delta is None


def test_constant_vs_variable_native_rank_displacement(case: Case) -> None:
    f = case.fixture
    from afre.statistical_models.schema import InterceptPolicy, SolverIdentity

    native = case.repo.get(FittedModelArtifact, f.upstream.upstream.covariances[0].model_id)
    supplied_spec = replace(
        case.repo.get(BaselineModelSpec, native.spec_id),
        family=ModelFamily.UNCONDITIONAL_MEAN,
        solver=SolverIdentity.REFERENCE_STATISTIC,
        l1_penalty=0.0,
        l2_penalty=0.0,
        regularize_intercept=False,
        intercept=InterceptPolicy.GLOBAL,
    )
    supplied_run = ModelEngine(case.repo).fit_model(supplied_spec, 40, 40, 40)
    model = case.repo.get(FittedModelArtifact, supplied_run.artifact_id)
    ids = tuple(
        i for i in f.spec.sample_ids if case.repo.get(ResearchSample, i).timestamp_ns == 60
    )
    predictions = ModelEngine(case.repo).predict_samples(
        model.fingerprint, ids, PredictionScope.VALIDATION
    )
    base = case.engine.register(
        replace(
            f.spec,
            sample_ids=ids,
            forecast_ids=tuple(
                i for i in f.spec.forecast_ids if forecast_source(case.repo, i).sample_id in ids
            ),
        )
    )
    other = case.engine.register(
        replace(base, forecast_ids=tuple(p.fingerprint for p in predictions))
    )
    env = next(d for d in f.environment_set.definitions if d.window and d.window.contains(60))
    members = tuple(
        case.engine.bind(env.fingerprint, i, constructed_ns=60).fingerprint for i in ids
    )
    d = case.engine.predictions(
        base.fingerprint, other.fingerprint, env.fingerprint, members, 100, 100
    )
    assert d.mean_rank_displacement == 1.0 and d.pearson is None and d.spearman is None
    assert d.top_k_overlap is not None and 0 <= d.top_k_overlap <= 1


def test_gaussian_scores_coverage_independent(case: Case) -> None:
    f = case.fixture
    metrics = case.engine.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
    from statistics import NormalDist

    for m in metrics:
        if m.name not in (
            StabilityMetricName.NLL,
            StabilityMetricName.COVERAGE,
            StabilityMetricName.WIDTH,
            StabilityMetricName.CRPS,
        ):
            continue
        expected = []
        for sid in m.sample_ids:
            source = next(
                forecast_source(case.repo, i)
                for i in f.spec.forecast_ids
                if forecast_source(case.repo, i).sample_id == sid
            )
            truth = case.repo.get(
                TargetVintage, case.repo.get(ResearchSample, sid).target_id or ""
            ).value
            assert truth is not None and source.law is not None
            from afre.probabilistic.artifacts import DistributionParameters

            assert isinstance(source.law, DistributionParameters)
            mu, sigma = source.law.location, source.law.scale
            low, high = (
                mu + sigma * NormalDist().inv_cdf(0.1),
                mu + sigma * NormalDist().inv_cdf(0.9),
            )
            z = (truth - mu) / sigma
            value = (
                math.log(sigma * math.sqrt(2 * math.pi)) + 0.5 * z * z
                if m.name is StabilityMetricName.NLL
                else float(low <= truth <= high)
                if m.name is StabilityMetricName.COVERAGE
                else high - low
                if m.name is StabilityMetricName.WIDTH
                else sigma
                * (
                    z * math.erf(z / math.sqrt(2))
                    + 2 * math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
                    - 1 / math.sqrt(math.pi)
                )
            )
            expected.append(value)
        assert m.value == pytest.approx(sum(expected) / len(expected), abs=1e-12)


@pytest.mark.parametrize(
    "limit",
    (
        "environments",
        "samples",
        "forecasts",
        "metrics",
        "features",
        "windows",
        "shift_cells",
        "serialized_bytes",
        "audit_nodes",
        "audit_depth",
        "artifacts",
    ),
)
def test_repository_bounds_fail_closed(case: Case, limit: str) -> None:
    f = case.fixture
    path = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with InvarianceRepository(path, replace(InvarianceBounds(), **{limit: 1})) as repo:
        e = InvarianceEngine(repo)
        with pytest.raises(ContractError):
            if limit in ("environments", "windows"):
                repo.get_any(f.environment_set.fingerprint)
            elif limit in ("audit_nodes", "audit_depth"):
                e.audit(f.spec.fingerprint)
            elif limit == "shift_cells":
                e.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
            elif limit == "artifacts":
                e.declare(
                    EnvironmentSet(
                        (replace(f.environment_set.definitions[0], environment_id="another"),),
                        40,
                    )
                )
            else:
                repo.get_any(f.spec.fingerprint)


def test_invariance_runtime_boundary_is_data_only() -> None:
    root = Path(__file__).resolve().parents[2] / "src/afre/invariance"
    forbidden = {
        "pickle",
        "joblib",
        "socket",
        "subprocess",
        "requests",
        "urllib",
        "ame",
        "mce",
        "eie",
        "options_engine",
    }
    for p in root.glob("*.py"):
        tree = ast.parse(p.read_text())
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                assert all(a.name.split(".")[0].lower() not in forbidden for a in n.names)
            if isinstance(n, ast.ImportFrom):
                assert (n.module or "").split(".")[0].lower() not in forbidden
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                assert n.func.id not in {"eval", "exec", "__import__"}


def test_no_empty_or_duplicate_membership_grid(case: Case) -> None:
    f = case.fixture
    for ms in ((), f.membership_ids[:-1], (*f.membership_ids, f.membership_ids[0])):
        with pytest.raises(ContractError):
            case.engine.evaluate(f.spec.fingerprint, ms, 100, 100)
    with pytest.raises(ContractError):
        case.engine.evaluate(f.spec.fingerprint, f.membership_ids, 100, 99)
    s = case.engine.register(
        replace(f.spec, intersection=SampleIntersectionPolicy.PAIRWISE_INTERSECTION)
    )
    with pytest.raises(ContractError):
        case.engine.evaluate(
            s.fingerprint,
            f.membership_ids,
            100,
            100,
            (f.environment_set.definitions[0].fingerprint,),
        )


def test_uncertainty_exact_additive_environment_metrics(case: Case) -> None:
    f = case.fixture
    sources = f.upstream.upstream.ids("mixture")
    target = f.spec.target
    defs = tuple(
        EnvironmentDefinition(
            name,
            EnvironmentKind.TIME_WINDOW,
            name,
            "1",
            "AFRE-declared",
            EnvironmentRule.TIME,
            target,
            40,
            window=StabilityTimeWindow(a, b),
        )
        for name, a, b in (("one", 40, 61), ("two", 50, 71))
    )
    envset = case.engine.declare(EnvironmentSet(defs, 40))
    samples = tuple(forecast_source(case.repo, i).sample_id for i in sources)
    spec = case.engine.register(
        replace(
            f.spec,
            environment_set_id=envset.fingerprint,
            sample_ids=samples,
            forecast_ids=sources,
            baseline_environment_id=None,
            uncertainty_ids=f.upstream.upstream.results("mixture"),
            metrics=(
                StabilityMetricName.PREDICTIVE_VARIANCE,
                StabilityMetricName.EXPERT_DISAGREEMENT,
                StabilityMetricName.COMPONENT_SHARE,
            ),
        )
    )
    members = tuple(
        case.engine.bind(d.fingerprint, i, constructed_ns=60).fingerprint
        for d in defs
        for i in samples
    )
    metrics = case.engine.evaluate(spec.fingerprint, members, 100, 100)
    assert all(m.value is not None for m in metrics)
    shares = [m.value for m in metrics if m.name is StabilityMetricName.COMPONENT_SHARE]
    assert all(v is not None and 0 <= v <= 1 for v in shares)
