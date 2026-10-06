"""Actual second SQLite writer cannot change frozen forecast/model/target identities."""

from dataclasses import replace

import pytest

from afre.statistical_models import ModelEngine
from afre.statistical_models.definitions import BaselineModelSpec
from afre.target_engine.market_data import TargetBar
from afre.uncertainty import (
    ParameterUncertaintySpec,
    UncertaintyEvaluationSpec,
    UncertaintyRepository,
    UncertaintySpec,
)
from examples.uncertainty_demo import corrected_mixture
from tests.uncertainty.conftest import Case


@pytest.mark.parametrize("kind", ["forecast", "model", "target", "all"])
def test_frozen_snapshot(case: Case, kind: str) -> None:
    d = case.result("mixture")
    spec = case.repo.get(UncertaintySpec, d.spec_id)
    covariance = case.fixture.covariances[0]
    parameter = case.repo.get(ParameterUncertaintySpec, covariance.spec_id)
    policy = UncertaintyEvaluationSpec(bucket_count=2)
    expected = case.engine.evaluate(case.fixture.results("mixture"), policy, 100, 100)
    path = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with UncertaintyRepository(path) as writer:
        counter = 0

        def correct() -> None:
            nonlocal counter
            counter += 1
            if kind in ("forecast", "all"):
                corrected_mixture(writer, d.forecast_id)
            if kind in ("model", "all"):
                from afre.statistical_models.artifacts import FittedModelArtifact

                old = writer.get(FittedModelArtifact, covariance.model_id)
                model_spec = writer.get(BaselineModelSpec, old.spec_id)
                ModelEngine(writer).fit_model(
                    model_spec, 40 + counter, 40 + counter, 40 + counter
                )
            if kind in ("target", "all"):
                identity = writer._connection.execute(
                    "SELECT fingerprint FROM target_artifacts "
                    "WHERE type_name='TargetBar' LIMIT 1"
                ).fetchone()[0]
                bar = writer.get(TargetBar, identity)
                with writer.transaction():
                    writer.put(
                        replace(
                            bar,
                            close=(bar.close or 0) + counter,
                            predecessor_id=bar.fingerprint,
                        )
                    )

        assert case.engine.decompose(spec, 60, snapshot_hook=correct) == d
        assert case.engine.fit_covariance(parameter, 40, snapshot_hook=correct) == covariance
        assert (
            case.engine.evaluate(
                case.fixture.results("mixture"), policy, 100, 100, snapshot_hook=correct
            )
            == expected
        )
