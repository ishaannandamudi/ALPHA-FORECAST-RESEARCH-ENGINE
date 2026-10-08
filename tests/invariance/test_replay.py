"""Fresh insertion reversals, all hash seeds, restart and actual horizons."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from afre.invariance import ComparabilityStatus
from afre.serialization import canonical_json
from examples.invariance_horizons import horizon_analyses
from tests.invariance.conftest import Base, Case
from tests.invariance.test_repository import legacy_copy


def replay(base: Base, path: Path, seed: str, reverse: bool) -> str:
    legacy_copy(base, path)
    env_path, spec_path = path.with_suffix(".environments.json"), path.with_suffix(".spec.json")
    env_path.write_text(canonical_json(base.fixture.environment_set))
    spec_path.write_text(canonical_json(base.fixture.spec))
    return subprocess.check_output(
        [
            sys.executable,
            "-m",
            "examples.invariance_replay",
            str(path),
            str(env_path),
            str(spec_path),
            "reverse" if reverse else "normal",
        ],
        env=dict(os.environ, PYTHONHASHSEED=seed),
        text=True,
        timeout=300,
    )


@pytest.fixture(scope="module")
def reference(base: Base, tmp_path_factory: pytest.TempPathFactory) -> str:
    return replay(base, tmp_path_factory.mktemp("inv-replay") / "reference.sqlite", "0", False)


@pytest.mark.parametrize("seed", ["0", "1", "42", "random"])
@pytest.mark.parametrize("reverse", [False, True])
def test_seed_order_restart(
    base: Base, tmp_path: Path, reference: str, seed: str, reverse: bool
) -> None:
    assert replay(base, tmp_path / "replay.sqlite", seed, reverse) == reference


def test_actual_hour_day_claims_separate(case: Case) -> None:
    ms = horizon_analyses(case.repo)
    assert len(ms) == 2 and ms[0].horizon_id != ms[1].horizon_id
    assert all(m.value is not None and m.status is ComparabilityStatus.COMPARABLE for m in ms)
    assert ms[0].target_id != ms[1].target_id
    assert (
        case.engine.compare(
            ms[0].fingerprint, ms[1].fingerprint, max(m.available_ns for m in ms)
        ).status
        is ComparabilityStatus.INCOMPARABLE
    )
