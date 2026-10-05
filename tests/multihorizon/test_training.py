"""Long labels, shared coefficients, exact TRAIN intersection and numerical reference."""

from dataclasses import replace

import pytest

from afre.multihorizon import (
    Architecture,
    HorizonForecastEntry,
    MultiHorizonRepository,
    SharedParameters,
    sharing_for,
)
from afre.multihorizon.alignment import aligned_rows, training_context
from afre.schema import ContractError
from afre.statistical_models.artifacts import PointForecast
from afre.statistical_models.linear_algebra import dot
from examples.calibration_demo import corrected_calibration_truth
from examples.multihorizon_demo import backbone_spec, build_fixture
from tests.multihorizon.conftest import Case


def test_longer_label_intersection(case: Case) -> None:
    run = case.fixture.run
    # Origin 30 short truth is completed/received at 35; long truth only at 45.
    assert len(run.train[0].sample_ids) > len(run.train[1].sample_ids)
    with case.repo.read_snapshot(), case.repo.validation_cache():
        _, matrices = training_context(case.repo, case.fixture.spec)
        assert any(r.origin.timestamp_ns == 30 for r in matrices[0].rows)
        assert not any(r.origin.timestamp_ns == 30 for r in matrices[1].rows)
        assert all(r.origin.timestamp_ns <= 20 for r in run.intersection)
        earlier = aligned_rows(case.repo, case.fixture.spec, matrices, 25)
        assert all(r.available_ns <= 25 for r in earlier)
        assert all(r.origin.timestamp_ns == 10 for r in earlier)


def test_shared_backbone_is_real_pooled_fit(case: Case) -> None:
    spec = backbone_spec(case.fixture)
    run = case.engine.fit(spec, 55, 55, 55)
    state = case.repo.get(SharedParameters, run.shared_parameters_id or "")
    assert state.sample_rows == run.intersection
    # A single x column with horizon-specific intercepts has a centered pooled slope.
    rows = run.intersection
    x = tuple(r.features[0][0] for r in rows)
    mx = sum(x) / len(x)
    denominator = (
        sum(w * sum((v - mx) ** 2 for v in x) for w in spec.horizon_weights)
        + spec.ridge_penalty
    )
    numerator = sum(
        w
        * sum(
            (v - mx) * (r.responses[h] - sum(t.responses[h] for t in rows) / len(rows))
            for v, r in zip(x, rows, strict=True)
        )
        for h, w in enumerate(spec.horizon_weights)
    )
    assert state.coefficients[0] == pytest.approx(numerator / denominator, abs=1e-14)
    for h, intercept in enumerate(state.intercepts):
        assert intercept == pytest.approx(
            sum(r.responses[h] for r in rows) / len(rows) - mx * state.coefficients[0]
        )
    bundle = case.fixture.bundles[0]
    points = tuple(
        case.engine.predict_shared(run.fingerprint, e.point_forecast_id or "", 60)
        for e in bundle.entries
    )
    for h, point in enumerate(points):
        assert point.value == pytest.approx(
            dot((40.0 + int(point.input.origin.instrument.value) - 1,), state.coefficients)
            + state.intercepts[h]
        )
    built = case.engine.build_bundle(
        run.fingerprint,
        bundle.origin,
        tuple(
            HorizonForecastEntry(p.target_definition_id, bundle.entries[h].state, p.fingerprint)
            for h, p in enumerate(points)
        ),
        60,
    )
    evaluated = case.engine.evaluate((built.fingerprint,), 75, 75)
    assert evaluated.weighted_mse is not None
    assert all(h.raw_scores == () for h in evaluated.horizons)
    assert case.engine.fit(spec, 55, 55, 55) == run


def test_shared_cutoff_excludes_long_future(case: Case) -> None:
    spec = replace(backbone_spec(case.fixture), shared_cutoff_ns=25)
    run = case.engine.fit(spec, 55, 55, 55)
    assert {r.origin.timestamp_ns for r in run.intersection} == {10}
    assert all(r.available_ns <= 25 for r in run.intersection)
    sample = case.fixture.run.intersection[0]
    old = case.repo.get(SharedParameters, run.shared_parameters_id or "")
    corrected_calibration_truth(case.repo, sample.target_ids[1], 110, 10.0)
    assert case.engine.fit(spec, 55, 55, 55) == run
    assert case.repo.get(SharedParameters, old.fingerprint) == old


@pytest.mark.parametrize(
    "changes",
    [
        {"point_spec_id": "point_model_id"},
        {"feature_set_id": "target_definition_id"},
        {"training_cutoff_ns": 39},
    ],
)
def test_binding_mismatch_fails_atomically(case: Case, changes: dict[str, object]) -> None:
    b = case.fixture.spec.bindings[0]
    kwargs = {
        key: getattr(b, val) if isinstance(val, str) else val for key, val in changes.items()
    }
    before = case.repo._connection.execute("SELECT count(*) FROM mh_artifacts").fetchone()[0]
    with pytest.raises(ContractError):
        spec = replace(
            case.fixture.spec,
            bindings=(replace(b, **kwargs), case.fixture.spec.bindings[1]),  # type: ignore[arg-type]
        )
        case.engine.fit(spec, 55, 55, 55)
    assert (
        case.repo._connection.execute("SELECT count(*) FROM mh_artifacts").fetchone()[0]
        == before
    )


def test_independent_different_features(tmp_path: object) -> None:
    from pathlib import Path
    from typing import cast

    with MultiHorizonRepository(cast(Path, tmp_path) / "different.sqlite") as repo:
        f = build_fixture(repo, feature_specific=True)
        assert len({b.feature_set_id for b in f.spec.bindings}) == 2
        with pytest.raises(ContractError, match="same exact features"):
            replace(
                f.spec,
                architecture=Architecture.SHARED_FEATURES_SEPARATE_MODELS,
                sharing=sharing_for(
                    f.spec.horizon_set, Architecture.SHARED_FEATURES_SEPARATE_MODELS
                ),
            )


def test_wrong_scaffold_and_future_shared_model(case: Case) -> None:
    run = case.engine.fit(backbone_spec(case.fixture), 65, 65, 65)
    point = case.fixture.bundles[0].entries[0].point_forecast_id or ""
    with pytest.raises(ContractError, match="unavailable"):
        case.engine.predict_shared(run.fingerprint, point, 65)
    with pytest.raises(ContractError, match="no shared"):
        case.engine.predict_shared(case.fixture.run.fingerprint, point, 60)
    assert case.repo.get(PointForecast, point).historical_admissible


def test_independent_horizon_cutoffs(case: Case) -> None:
    from afre.research_datasets import DatasetEngine
    from afre.research_datasets.splits import SplitDefinition
    from afre.statistical_models import ModelEngine
    from afre.statistical_models.definitions import BaselineModelSpec
    from afre.time import TimeRange

    binding = case.fixture.spec.bindings[1]
    fold = case.repo.resolve_fold(binding.fold_id)
    split = case.repo.get(SplitDefinition, fold.split_definition_id)
    revised = DatasetEngine(case.repo).build_split(
        fold.dataset_id,
        replace(split, name="split.long_early", train=TimeRange(10, 30), training_cutoff_ns=30),
    )
    base = replace(
        case.repo.get(BaselineModelSpec, binding.point_spec_id), fold_id=revised.fold_ids[0]
    )
    point = ModelEngine(case.repo).fit_model(base, 30, 30, 30)
    spec = replace(
        case.fixture.spec,
        bindings=(
            case.fixture.spec.bindings[0],
            replace(
                binding,
                point_spec_id=base.fingerprint,
                point_model_id=point.artifact_id,
                fold_id=revised.fold_ids[0],
                training_cutoff_ns=30,
                probability_spec_id=None,
                probability_model_id=None,
                calibration_spec_id=None,
                calibration_state_id=None,
            ),
        ),
    )
    run = case.engine.fit(spec, 55, 55, 55)
    assert tuple(t.cutoff_ns for t in run.train) == (40, 30)
    assert {r.origin.timestamp_ns for r in run.intersection} == {10}
    with pytest.raises(ContractError):
        case.engine.evaluate((), 75, 75)
