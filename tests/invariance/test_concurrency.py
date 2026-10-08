"""A real second SQLite writer cannot replace exact frozen environment or target evidence."""

from dataclasses import replace

import pytest

from afre.cross_sectional import CrossSectionEngine
from afre.event_conditioned import EventEngine
from afre.invariance import EnvironmentSet, InvarianceRepository
from afre.regime_conditioned import RegimeEngine
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from afre.statistical_models import ModelEngine
from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec
from afre.target_engine.market_data import TargetBar
from examples.cross_sectional_demo import group
from examples.event_conditioned_demo import event
from examples.regime_conditioned_demo import snapshot, taxonomy
from tests.invariance.conftest import Case


@pytest.mark.parametrize(
    "kind", ("environment", "regime", "event", "group", "forecast", "target", "all")
)
def test_real_writer_frozen_analysis(case: Case, kind: str) -> None:
    f = case.fixture
    expected = case.engine.evaluate(f.spec.fingerprint, f.membership_ids, 100, 100)
    path = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with InvarianceRepository(path) as writer:

        def correction() -> None:
            s = writer.get(ResearchSample, f.spec.sample_ids[0])
            if kind in ("environment", "all"):
                d = replace(
                    f.environment_set.definitions[0],
                    version="revision2",
                    label="corrected declaration",
                    declared_ns=90,
                )
                from afre.invariance import InvarianceEngine

                InvarianceEngine(writer).declare(EnvironmentSet((d,), 90))
            if kind in ("regime", "all"):
                RegimeEngine(writer).publish_snapshot(
                    replace(snapshot(taxonomy(), s, received=90), revision="corrected")
                )
            if kind in ("event", "all"):
                EventEngine(writer).publish_event(
                    event(s, "corrected-event", received=90, revision="2")
                )
            if kind in ("group", "all"):
                CrossSectionEngine(writer).publish_group(
                    group(s.security, "corrected-group", 90)
                )
            if kind in ("forecast", "all"):
                point = writer.get_any(f.spec.forecast_ids[0])
                from afre.probabilistic.artifacts import ProbabilisticForecast

                assert isinstance(point, ProbabilisticForecast)
                rawpoint = writer.get(PointForecast, point.point_forecast_id)
                candidates = tuple(
                    writer.get(FittedModelArtifact, row[0])
                    for row in writer._connection.execute(
                        "SELECT fingerprint FROM m_artifacts "
                        "WHERE type_name='FittedModelArtifact' ORDER BY fingerprint"
                    )
                )
                alternate = next(
                    m
                    for m in candidates
                    if m.fingerprint != rawpoint.model_artifact_id
                    and writer.get(BaselineModelSpec, m.spec_id).target.fingerprint
                    == f.spec.target.fingerprint
                    and m.available_ns <= rawpoint.input.origin.availability_cutoff_ns
                )
                corrected = ModelEngine(writer).predict(
                    alternate.fingerprint, rawpoint.input, rawpoint.computed_ns
                )
                assert corrected.fingerprint != rawpoint.fingerprint
            if kind in ("target", "all"):
                identity = writer._connection.execute(
                    "SELECT fingerprint FROM target_artifacts "
                    "WHERE type_name='TargetBar' LIMIT 1"
                ).fetchone()[0]
                bar = writer.get(TargetBar, identity)
                with writer.transaction():
                    writer.put(
                        replace(bar, close=(bar.close or 0) + 1, predecessor_id=bar.fingerprint)
                    )

        actual = case.engine.evaluate(
            f.spec.fingerprint, f.membership_ids, 100, 100, snapshot_hook=correction
        )
        assert tuple(canonical_json(m) for m in actual) == tuple(
            canonical_json(m) for m in expected
        )
    assert all(case.repo.get_any(m.fingerprint) == m for m in expected)
