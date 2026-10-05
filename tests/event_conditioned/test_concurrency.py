"""Second-writer revisions cannot change a frozen exact-reference computation."""

from dataclasses import replace

from afre.cross_sectional import CrossSectionEngine
from afre.event_conditioned import EventEngine, EventReference, EventRepository
from afre.event_conditioned.artifacts import EventConditionedObservation
from afre.serialization import canonical_json
from afre.target_engine.models import TargetVintage
from examples.cross_sectional_demo import external
from examples.feature_store_demo import clocks
from tests.event_conditioned.conftest import Case
from tests.event_conditioned.test_models import first


def test_second_writer_corrects_event_target_and_reaction(case: Case) -> None:
    p = first(case)
    o = case.repo.get(EventConditionedObservation, p.observation_id)
    e = case.repo.get(EventReference, o.event_id or "")
    target = case.repo.get(TargetVintage, o.target_id or "")
    training = case.repo.get(
        EventConditionedObservation, case.fixture.training_observation_ids[0]
    )
    training_target = case.repo.get(TargetVintage, training.target_id or "")
    old_model, old_forecast = canonical_json(case.fixture.model), canonical_json(p)
    tables = ("ec_artifacts", "target_artifacts", "cs_artifacts")
    with EventRepository(case.path) as writer:
        corrected = replace(e, revision="concurrent-correction")

        def insert() -> None:
            before = tuple(
                case.repo._connection.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in tables
            )
            EventEngine(writer).publish_event(corrected)
            CrossSectionEngine(writer).publish_external(external(p.security, 60, 99.0, 90))
            with writer.transaction():
                writer.put(replace(target, clocks=clocks(110)))
                writer.put(replace(training_target, clocks=clocks(110)))
            after = tuple(
                case.repo._connection.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in tables
            )
            assert before == after

        rebuilt = case.engine.forecast(
            p.model_id,
            p.observation_id,
            p.base_forecast_id,
            60,
            p.base_probability_id,
            snapshot_hook=insert,
        )
    assert rebuilt == p
    assert canonical_json(case.repo.get(type(p), p.fingerprint)) == old_forecast
    assert (
        case.engine.fit(case.fixture.spec, case.fixture.training_observation_ids, 40, 40, 40)
        == case.fixture.model
    )
    assert canonical_json(case.fixture.model) == old_model
    new = case.engine.observe(case.fixture.spec, o.sample_id, (corrected.fingerprint,))[0]
    changed = case.engine.forecast(
        p.model_id, new.fingerprint, p.base_forecast_id, 60, p.base_probability_id
    )
    assert changed.fingerprint != p.fingerprint


def test_open_observation_snapshot_excludes_new_event(case: Case) -> None:
    p = first(case)
    o = case.repo.get(EventConditionedObservation, p.observation_id)
    e = case.repo.get(EventReference, o.event_id or "")
    with EventRepository(case.path) as writer:
        corrected = replace(e, revision="observation-correction")

        def insert() -> None:
            EventEngine(writer).publish_event(corrected)

        result = case.engine.observe(
            case.fixture.spec,
            o.sample_id,
            (e.fingerprint,),
            snapshot_hook=insert,
        )
    assert result == (o,)
