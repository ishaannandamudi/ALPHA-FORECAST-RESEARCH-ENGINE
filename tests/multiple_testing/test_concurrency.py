"""A real second SQLite writer cannot mutate pinned trial, family or registry evidence."""

from dataclasses import replace

from afre.multiple_testing import (
    FamilyCompleteness,
    MultipleTestingEngine,
    MultipleTestingRepository,
)
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from afre.target_engine.market_data import TargetBar
from afre.target_engine.models import TargetVintage
from tests.multiple_testing.conftest import TestingCase as MTCase


def test_trial_frozen_truth_with_native_writer(mt_case: MTCase) -> None:
    p = mt_case.fixture.plan("test-0")
    family = mt_case.fixture.family
    filename = mt_case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    sample = mt_case.repo.resolve(ResearchSample, p.sample_ids[0])
    assert sample.target_id is not None
    truth = mt_case.repo.resolve(TargetVintage, sample.target_id)
    assert truth.endpoint_bar_id is not None
    bar = mt_case.repo.resolve(TargetBar, truth.endpoint_bar_id)
    with MultipleTestingRepository(filename) as writer:

        def correction() -> None:
            with writer.transaction():
                writer.put(
                    replace(bar, close=(bar.close or 0) + 999, predecessor_id=bar.fingerprint)
                )

        t = mt_case.engine.complete(
            p.fingerprint,
            family.fingerprint,
            100,
            100,
            test_identity="snapshot-native-test",
            snapshot_hook=correction,
        )
    assert any(o.truth_id == truth.fingerprint for o in t.observations)
    assert mt_case.repo.get_any(t.fingerprint) == t
    assert mt_case.repo.get_any(family.fingerprint) == family


def test_registry_and_adjustment_frozen_against_same_cutoff_new_trial(mt_case: MTCase) -> None:
    f = mt_case.fixture.family
    p, q = mt_case.fixture.plan("phase-5"), mt_case.fixture.plan("phase-6")
    t = mt_case.engine.complete(p.fingerprint, f.fingerprint, 100, 100)
    filename = mt_case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with MultipleTestingRepository(filename) as writer:

        def addition() -> None:
            MultipleTestingEngine(writer).complete(q.fingerprint, f.fingerprint, 100, 100)

        registry = mt_case.engine.registry(100, 100, snapshot_hook=addition)
    assert registry.trial_ids == (t.fingerprint,)
    assert len(mt_case.engine.registry(100, 100).trial_ids) == 2
    original = canonical_json(registry)
    results = mt_case.engine.analyze(
        f.fingerprint, (t.fingerprint,), FamilyCompleteness.PARTIAL, 100, 100
    )
    encoded = tuple(canonical_json(a) for a in results)
    with MultipleTestingRepository(filename) as writer:
        r = mt_case.fixture.plan("phase-13")

        def later() -> None:
            MultipleTestingEngine(writer).complete(r.fingerprint, f.fingerprint, 100, 100)

        replay = mt_case.engine.analyze(
            f.fingerprint,
            (t.fingerprint,),
            FamilyCompleteness.PARTIAL,
            100,
            100,
            snapshot_hook=later,
        )
    assert tuple(canonical_json(a) for a in replay) == encoded
    assert canonical_json(mt_case.repo.get_any(registry.fingerprint)) == original


def test_native_forecast_correction_new_opportunity_old_evidence_fixed(mt_case: MTCase) -> None:
    from afre.multiple_testing import CorrectionMethod, DependenceAssumption, HypothesisFamily
    from afre.statistical_models import ModelEngine
    from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
    from afre.statistical_models.definitions import BaselineModelSpec
    from examples.multiple_testing_fixture import declare_plan
    from tests.multiple_testing.helpers import one_family

    p, f = one_family(mt_case, "phase-5")
    t = mt_case.engine.complete(p.fingerprint, f.fingerprint, 100, 100)
    old = mt_case.engine.analyze(
        f.fingerprint, (t.fingerprint,), FamilyCompleteness.COMPLETE, 100, 100
    )[0]
    old_bytes = canonical_json(old)
    with mt_case.repo.read_snapshot(), mt_case.repo.validation_cache():
        raw = mt_case.repo.resolve(PointForecast, p.source_ids[0])
        target = mt_case.repo.resolve(
            BaselineModelSpec,
            mt_case.repo.resolve(FittedModelArtifact, raw.model_artifact_id).spec_id,
        ).target
        models = tuple(
            mt_case.repo.resolve(FittedModelArtifact, i)
            for (i,) in mt_case.repo._connection.execute(
                "SELECT fingerprint FROM m_artifacts WHERE type_name='FittedModelArtifact' "
                "ORDER BY fingerprint"
            )
        )
        alternate = next(
            m
            for m in models
            if m.fingerprint != raw.model_artifact_id
            and mt_case.repo.resolve(BaselineModelSpec, m.spec_id).target == target
            and m.available_ns <= raw.input.origin.availability_cutoff_ns
        )
        inputs = tuple(mt_case.repo.resolve(PointForecast, i).input for i in p.source_ids)
    corrected = tuple(
        ModelEngine(mt_case.repo)
        .predict(alternate.fingerprint, v, v.origin.timestamp_ns)
        .fingerprint
        for v in inputs
    )
    q = declare_plan(
        mt_case.repo,
        "corrected-native-forecast",
        "corrected-forecast",
        5,
        min(corrected),
        corrected,
    )
    qf = mt_case.engine.family(
        HypothesisFamily(
            "corrected-forecast",
            (q.fingerprint,),
            CorrectionMethod.HOLM,
            0.05,
            DependenceAssumption.UNKNOWN,
            40,
            True,
        )
    )
    qt = mt_case.engine.complete(q.fingerprint, qf.fingerprint, 100, 100)
    assert q.fingerprint != p.fingerprint and qt.fingerprint != t.fingerprint
    assert canonical_json(mt_case.repo.get_any(old.fingerprint)) == old_bytes
    assert mt_case.repo.get_any(t.fingerprint) == t
