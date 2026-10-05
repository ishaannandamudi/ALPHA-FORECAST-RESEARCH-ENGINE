"""Seeds, all provider/security insertion orders and restart yield identical bytes."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def replay(path: Path, seed: str, reverse: bool) -> str:
    environment = dict(os.environ, PYTHONHASHSEED=seed)
    root = Path(__file__).resolve().parents[2]
    return subprocess.check_output(
        [
            sys.executable,
            "-m",
            "tests.cross_sectional.replay_worker",
            str(path),
            "reverse" if reverse else "normal",
        ],
        cwd=root,
        env=environment,
        text=True,
        timeout=120,
    )


@pytest.fixture(scope="module")
def reference(tmp_path_factory: pytest.TempPathFactory) -> str:
    return replay(tmp_path_factory.mktemp("cross-reference") / "research.sqlite", "0", False)


@pytest.mark.parametrize("seed", ["0", "1", "42", "random"])
@pytest.mark.parametrize("reverse", [False, True])
def test_hash_seed_reverse_restart(
    tmp_path: Path, reference: str, seed: str, reverse: bool
) -> None:
    assert replay(tmp_path / "research.sqlite", seed, reverse) == reference
