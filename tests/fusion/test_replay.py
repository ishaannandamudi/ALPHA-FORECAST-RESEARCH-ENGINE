"""Fresh interpreters across seeds and source/sample/spec/request reversal."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from afre.fusion import FusionEngine, FusionRepository
from examples.fusion_demo import run
from examples.fusion_fixture import FusionFixture


@pytest.mark.parametrize("seed", ("0", "1", "42", "random"))
def test_seed_and_reversed_order(seed: str, tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": "src:."}
    results = []
    for reverse in (False, True):
        command = [sys.executable, "-m", "examples.fusion_demo", "--core"]
        if reverse:
            command.append("--reverse")
        completed = subprocess.run(
            command, env=env, capture_output=True, text=True, check=True, timeout=120
        )
        results.append(json.loads(completed.stdout))
    assert results[0] == results[1]
    with FusionRepository(tmp_path / "local.sqlite"):
        pass
    expected = run(tmp_path / "expected.sqlite", include_native=False)
    assert results[0] == json.loads(json.dumps(expected))


def test_failed_attempt_counted_and_pool_atomic(
    fusion_case: tuple[FusionRepository, FusionFixture],
) -> None:
    repo, f = fusion_case
    from dataclasses import replace

    from afre.schema import ContractError
    from afre.statistical_models.artifacts import PointForecast

    e = FusionEngine(repo)
    e.declare(f.spec)
    e.declare(replace(f.spec, name="failed-attempt"))
    failed_spec = replace(f.spec, name="failed-attempt")
    anchors = tuple(
        row[0]
        for row in repo._connection.execute(
            "SELECT fingerprint FROM m_artifacts WHERE type_name='PointForecast'"
        )
    )
    assert all(repo.get(PointForecast, i).input.sample_id in f.validation for i in anchors)
    pool = e.trial_pool(((failed_spec.fingerprint, ()),), anchors)
    assert pool.failed_spec_ids == (failed_spec.fingerprint,)
    count = repo._connection.execute("SELECT count(*) FROM mt_artifacts").fetchone()[0]
    with pytest.raises(ContractError):
        e.trial_pool(((f.spec.fingerprint, ()),))
    assert repo._connection.execute("SELECT count(*) FROM mt_artifacts").fetchone()[0] == count
