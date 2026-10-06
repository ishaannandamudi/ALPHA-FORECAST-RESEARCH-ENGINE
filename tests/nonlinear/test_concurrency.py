"""Second writers publish new source/transform/truth identities; pinned reads survive."""

from dataclasses import replace

import pytest

from afre.cross_sectional.engine import CrossSectionEngine
from afre.cross_sectional.external import ExternalSignal
from afre.nonlinear import (
    FittedTransformArtifact,
    InteractionDefinition,
    InteractionMatrix,
    NonlinearEngine,
    NonlinearRepository,
    ScalarSourceKind,
)
from afre.serialization import canonical_json
from afre.target_engine.market_data import TargetBar
from tests.nonlinear.conftest import Case


@pytest.mark.parametrize("kind", ["source", "transform", "target", "all"])
def test_frozen_fit_prediction_and_evaluation(case: Case, kind: str) -> None:
    forecast = case.forecast
    model = case.fixture.models[0]
    spec = case.fixture.specs[0]
    matrix = case.repo.get(InteractionMatrix, model.matrix_id)
    scalar = next(
        s for s in case.inputs.scalars if s.definition.kind is ScalarSourceKind.EXTERNAL_SIGNAL
    )
    source = case.repo.get(ExternalSignal, scalar.source_id)
    evaluation = case.engine.evaluate(case.fixture.forecast_ids[0], 100, 100)
    with NonlinearRepository(case.path) as writer:
        counter = 0

        def correct() -> None:
            nonlocal counter
            counter += 1
            if kind in ("source", "all"):
                assert isinstance(source.value, (int, float))
                CrossSectionEngine(writer).publish_external(
                    replace(source, value=float(source.value or 0.0) + counter)
                )
            if kind in ("transform", "all"):
                state = writer.get(FittedTransformArtifact, model.transform_ids[0])
                definition = writer.get(InteractionDefinition, state.definition_id)
                NonlinearEngine(writer).fit_transform(
                    spec,
                    definition,
                    case.fixture.train_ids,
                    40 + counter,
                    40 + counter,
                    40 + counter,
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
                            close=(bar.close or 0.0) + counter,
                            predecessor_id=bar.fingerprint,
                        )
                    )

        predicted = case.engine.predict(
            model.fingerprint,
            forecast.input_id,
            forecast.computed_ns,
            forecast.probability.base_forecast_id if forecast.probability else None,
            snapshot_hook=correct,
        )
        fitted = case.engine.fit(spec, matrix.fingerprint, 40, 40, 40, snapshot_hook=correct)
        evaluated = case.engine.evaluate(
            case.fixture.forecast_ids[0], 100, 100, snapshot_hook=correct
        )
        rebuilt = case.engine.matrix(
            spec, case.fixture.train_ids, model.transform_ids, 40, snapshot_hook=correct
        )
    assert canonical_json(predicted) == canonical_json(forecast)
    assert fitted == model and evaluated == evaluation and rebuilt == matrix
