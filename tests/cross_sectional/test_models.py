"""Real TRAIN-relative fitting over the unchanged AFRE-5 admission and QR solver."""

from dataclasses import replace

import pytest

from afre.cross_sectional import CrossSectionModelSpec, ScoreSource, ScoreSpec, TargetCentering
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.statistical_models import ModelEngine, ModelFamily, PredictionScope
from afre.statistical_models.artifacts import DesignMatrix
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.schema import SolverIdentity
from afre.target_engine.models import TargetVintage
from tests.cross_sectional.conftest import Case


@pytest.mark.parametrize("centering", list(TargetCentering))
def test_relative_fit_and_target_free_prediction(
    case: Case, centering: TargetCentering, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = case.repo.get(
        BaselineModelSpec, case.fixture.upstream.spec.bindings[0].point_spec_id
    )
    base = replace(
        base,
        family=ModelFamily.CROSS_SECTIONAL_LINEAR,
        solver=SolverIdentity.PIVOTED_HOUSEHOLDER_QR,
    )
    run = ModelEngine(case.repo).fit_model(base, 40, 40, 40)
    spec = CrossSectionModelSpec(run.artifact_id, centering)
    model = case.engine.fit(spec, 40, 40, 40)
    assert model == case.engine.fit(spec, 40, 40, 40)
    matrix = case.repo.get(DesignMatrix, model.matrix_id)
    rows = {r.sample_id: r for r in matrix.rows}
    assert sum(len(g) for g in model.train_groups) == len(matrix.rows)
    for peers, mean in zip(model.train_groups, model.train_centers, strict=True):
        assert len({rows[s].origin.timestamp_ns for s in peers}) == 1
        assert all(rows[s].data_available_ns <= 40 for s in peers)
        expected = (
            sum(rows[s].response for s in peers) / len(peers)
            if centering is TargetCentering.WITHIN_ORIGIN
            else 0.0
        )
        assert mean == pytest.approx(expected)
    sample_id = case.fixture.upstream.deployment[0][0].input.sample_id
    assert sample_id is not None
    scaffold = ModelEngine(case.repo).predict_samples(
        run.artifact_id, (sample_id,), PredictionScope.VALIDATION
    )[0]
    original = case.repo.get

    def reject_truth(cls: type[TargetVintage], identity: str) -> TargetVintage:
        assert cls is not TargetVintage
        return original(cls, identity)

    monkeypatch.setattr(case.repo, "get", reject_truth)
    prediction = case.engine.predict(model.fingerprint, scaffold.fingerprint, 60)
    assert prediction.available_ns == 60
    assert prediction == case.engine.predict(model.fingerprint, scaffold.fingerprint, 60)


def test_relative_rejects_non_cross_sectional_model(case: Case) -> None:
    with pytest.raises(ContractError, match="cross-sectional linear"):
        case.engine.fit(
            CrossSectionModelSpec(case.fixture.upstream.spec.bindings[0].point_model_id),
            40,
            40,
            40,
        )


def test_relative_score_and_complete_lineage(case: Case) -> None:
    f = case.fixture
    base = case.repo.get(BaselineModelSpec, f.upstream.spec.bindings[0].point_spec_id)
    base = replace(
        base,
        family=ModelFamily.CROSS_SECTIONAL_LINEAR,
        solver=SolverIdentity.PIVOTED_HOUSEHOLDER_QR,
    )
    run = ModelEngine(case.repo).fit_model(base, 40, 40, 40)
    model = case.engine.fit(
        CrossSectionModelSpec(run.artifact_id, TargetCentering.WITHIN_ORIGIN), 40, 40, 40
    )
    samples = tuple(
        p.input.sample_id for p in f.upstream.deployment[0] if p.input.sample_id is not None
    )
    scaffold = ModelEngine(case.repo).predict_samples(
        run.artifact_id, samples, PredictionScope.VALIDATION
    )
    predictions = tuple(
        case.engine.predict(model.fingerprint, p.fingerprint, 60) for p in scaffold
    )
    sources = tuple(
        (
            case.repo.get(ResearchSample, p.input.sample_id or "").security.fingerprint,
            prediction.fingerprint,
        )
        for p, prediction in zip(scaffold, predictions, strict=True)
    )
    spec = replace(
        f.native_spec, score=ScoreSpec(ScoreSource.POINT_PREDICTION, model.fingerprint)
    )
    rank = case.engine.build_ranking(spec, sources)
    assert rank.ranked_count == len(samples)
    audit = case.engine.audit_lineage(rank.fingerprint)
    assert model.matrix_id in audit.evidence_ids and run.fingerprint in audit.evidence_ids
    assert case.repo.audit() > 0


def test_relative_rejects_sparse_train_origin(case: Case) -> None:
    base = case.repo.get(
        BaselineModelSpec, case.fixture.upstream.spec.bindings[0].point_spec_id
    )
    base = replace(
        base,
        family=ModelFamily.CROSS_SECTIONAL_LINEAR,
        solver=SolverIdentity.PIVOTED_HOUSEHOLDER_QR,
    )
    run = ModelEngine(case.repo).fit_model(base, 40, 40, 40)
    with pytest.raises(ContractError, match="too few"):
        case.engine.fit(
            CrossSectionModelSpec(run.artifact_id, minimum_train_peers=10), 40, 40, 40
        )


def test_relative_fit_historical_clocks(case: Case) -> None:
    base = case.repo.get(
        BaselineModelSpec, case.fixture.upstream.spec.bindings[0].point_spec_id
    )
    base = replace(
        base,
        family=ModelFamily.CROSS_SECTIONAL_LINEAR,
        solver=SolverIdentity.PIVOTED_HOUSEHOLDER_QR,
    )
    run = ModelEngine(case.repo).fit_model(base, 40, 40, 40)
    spec = CrossSectionModelSpec(run.artifact_id)
    with pytest.raises(ContractError, match="before evidence"):
        case.engine.fit(spec, 39, 40, 40)
    model = case.engine.fit(spec, 40, 40, 61)
    scaffold = case.fixture.upstream.deployment[0][0].point_forecast_id
    with pytest.raises(ContractError, match="relative prediction"):
        case.engine.predict(model.fingerprint, scaffold, 60)
