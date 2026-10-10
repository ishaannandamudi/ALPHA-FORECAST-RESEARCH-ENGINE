"""Actual concurrent SQLite writer corrections cannot rewrite frozen fusion inputs."""

from dataclasses import replace
from pathlib import Path
from queue import Queue
from threading import Thread

from afre.fusion import (
    ExternalFusionOutput,
    FusionArtifact,
    FusionEngine,
    FusionObservation,
    FusionRepository,
)
from afre.fusion.external import ExternalFusionDefinition
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from afre.target_engine.market_data import TargetBar
from afre.target_engine.models import TargetVintage
from examples.fusion_fixture import FusionFixture, apply_partition
from tests.fusion.test_workflow import learned

Case = tuple[FusionRepository, FusionFixture]


def test_concurrent_source_target_spec_corrections(fusion_case: Case) -> None:
    repo, f = fusion_case
    repo._connection.execute("PRAGMA journal_mode=WAL")
    db = Path(repo._connection.execute("PRAGMA database_list").fetchone()[2])
    e = FusionEngine(repo)
    artifact = learned(repo, f)
    ids = apply_partition(repo, f, artifact.fingerprint, f.validation)
    pool = e.trial_pool(((artifact.spec_id, ids),))
    baseline = e.evaluate(ids, pool.fingerprint, 100, 100)
    errors: Queue[BaseException] = Queue()

    def writer() -> None:
        try:
            with FusionRepository(db) as other:
                obs = other.get(FusionObservation, f.observations(f.validation[0])[0])
                raw = other.get(ExternalFusionOutput, obs.output_id)
                replacement = replace(raw, value=555.0, revision="concurrent")
                FusionEngine(other).external(
                    other.get(ExternalFusionDefinition, raw.definition_id), (replacement,)
                )
                sample = other.get(ResearchSample, f.validation[0])
                assert sample.target_id is not None
                target = other.get(TargetVintage, sample.target_id)
                assert target.endpoint_bar_id is not None
                bar = other.get(TargetBar, target.endpoint_bar_id)
                from afre.feature_store.models import AvailabilityEvidence

                with other.transaction():
                    other.put(
                        replace(
                            bar,
                            close=555.0,
                            clocks=AvailabilityEvidence(100, 100, 100, 100),
                            predecessor_id=bar.fingerprint,
                        )
                    )
                FusionEngine(other).declare(replace(f.spec, name="concurrent-additional-spec"))
        except BaseException as error:
            errors.put(error)

    def hook() -> None:
        thread = Thread(target=writer)
        thread.start()
        thread.join(30)
        assert not thread.is_alive()
        if not errors.empty():
            raise errors.get()

    replay = e.evaluate(ids, pool.fingerprint, 100, 100, snapshot_hook=hook)
    assert canonical_json(replay) == canonical_json(baseline)
    assert canonical_json(repo.resolve(FusionArtifact, artifact.fingerprint)) == canonical_json(
        artifact
    )
