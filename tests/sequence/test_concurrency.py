"""Real second writer corrections cannot contaminate frozen computations."""

from dataclasses import replace

import pytest

from afre.cross_sectional.engine import CrossSectionEngine
from afre.cross_sectional.external import ExternalSignal
from afre.nonlinear import NonlinearEngine, ScalarInput
from afre.sequence import (
    SequenceEngine,
    SequenceObservation,
    SequenceRepository,
    SequenceSnapshot,
)
from afre.target_engine.market_data import TargetBar
from tests.sequence.conftest import Case


@pytest.mark.parametrize("kind", ["source", "target", "model", "all"])
def test_frozen_read(case: Case, kind: str) -> None:
    f, model, spec = case.forecast, case.fixture.models[0], case.fixture.specs[0]
    snap = case.repo.get(SequenceSnapshot, f.snapshot_id)
    expected = case.engine.evaluate(case.fixture.forecasts[0], 100, 100)
    old = next(
        case.repo.get(SequenceObservation, i)
        for i in snap.candidate_ids
        if case.repo.get(SequenceObservation, i).feature_id == case.micro.fingerprint
    )
    scalar = case.repo.get(ScalarInput, old.source_id)
    source = case.repo.get(ExternalSignal, scalar.source_id)
    with SequenceRepository(
        case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    ) as writer:
        counter = 0

        def correct() -> None:
            nonlocal counter
            counter += 1
            if kind in ("source", "all"):
                correction = replace(source, value=float(source.value or 0) + counter)
                CrossSectionEngine(writer).publish_external(correction)
                projected = NonlinearEngine(writer).scalar(
                    correction.fingerprint, scalar.origin
                )
                SequenceEngine(writer).observation(case.micro, projected.fingerprint)
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
            if kind in ("model", "all"):
                SequenceEngine(writer).fit(
                    spec, model.dataset_id, 40 + counter, 40 + counter, 40 + counter
                )

        rebuilt = case.engine.snapshot(
            snap.origin, spec.features, spec.window, 60, snapshot_hook=correct
        )
        assert rebuilt == snap
        assert (
            case.engine.predict(
                f.model_id,
                f.sample_id,
                f.snapshot_id,
                60,
                f.probability.base_forecast_id if f.probability else None,
                snapshot_hook=correct,
            )
            == f
        )
        assert (
            case.engine.fit(spec, model.dataset_id, 40, 40, 40, snapshot_hook=correct) == model
        )
        assert (
            case.engine.evaluate(case.fixture.forecasts[0], 100, 100, snapshot_hook=correct)
            == expected
        )
