"""A real second SQLite writer cannot change exact frozen signal/projection/target evidence."""

from dataclasses import replace

import pytest

from afre.orthogonalization import OrthogonalizationEngine, OrthogonalizationRepository
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.serialization import canonical_json
from afre.target_engine.market_data import TargetBar
from examples.orthogonalization_fixture import generic_source
from tests.orthogonalization.conftest import Case


@pytest.mark.parametrize("kind", ["candidate", "reference", "projection", "target", "all"])
def test_real_writer_snapshot(case: Case, kind: str) -> None:
    f = case.fixture
    expected = case.engine.evaluate(
        f.residual_ids(Partition.VALIDATION), 100, 100, target_diagnostics=True
    )
    value = f.residuals[0]
    before = canonical_json(f.projection), canonical_json(value), canonical_json(expected)
    path = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with OrthogonalizationRepository(path) as writer:
        ew = OrthogonalizationEngine(writer)
        counter = 0

        def correction() -> None:
            nonlocal counter
            counter += 1
            if kind in ("candidate", "reference", "all"):
                ref = f.spec.candidate if kind == "candidate" else f.spec.references[0]
                sample = writer.get(ResearchSample, value.sample_id)
                ew.publish_generic(
                    generic_source(ref, sample, 999.0, "concurrent-" + str(counter), 10)
                )
            if kind in ("projection", "all"):
                ew.fit(f.spec, f.projection.row_ids, 41 + counter)
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

        assert (
            case.engine.fit(f.spec, f.projection.row_ids, 40, snapshot_hook=correction)
            == f.projection
        )
        assert (
            case.engine.residual(
                value.projection_id, value.row_id, value.computed_ns, snapshot_hook=correction
            )
            == value
        )
        assert (
            case.engine.evaluate(
                f.residual_ids(Partition.VALIDATION),
                100,
                100,
                target_diagnostics=True,
                snapshot_hook=correction,
            )
            == expected
        )
    assert before == (
        canonical_json(case.repo.get_any(f.projection.fingerprint)),
        canonical_json(case.repo.get_any(value.fingerprint)),
        canonical_json(case.repo.get_any(expected.fingerprint)),
    )
