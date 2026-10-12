"""Actual source correction propagates through independent immutable native layers."""

from pathlib import Path

from afre.service import AFREService, ServiceRepository, canonical_json
from examples.release_workflows import correction_workflow


def test_feature_to_snapshot_correction(tmp_path: Path) -> None:
    path = tmp_path / "correction.sqlite"
    with ServiceRepository(path) as repo:
        evidence = correction_workflow(repo)
        original = AFREService(repo).get_snapshot(evidence.original_snapshot)
        updated = AFREService(repo).get_snapshot(evidence.corrected_snapshot)
        frozen = canonical_json(original)
        assert original != updated
    with ServiceRepository(path) as repo:
        assert (
            canonical_json(AFREService(repo).get_snapshot(evidence.original_snapshot)) == frozen
        )
        assert AFREService(repo).get_snapshot(evidence.corrected_snapshot) == updated
