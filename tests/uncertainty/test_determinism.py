"""Hash seeds 0/1/42/random, reversed source/components/requests and restart."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def replay(path: Path, seed: str, reverse: bool) -> str:
    return subprocess.check_output(
        [
            sys.executable,
            "-m",
            "tests.uncertainty.replay_worker",
            str(path),
            "reverse" if reverse else "normal",
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=dict(os.environ, PYTHONHASHSEED=seed),
        text=True,
        timeout=300,
    )


@pytest.fixture(scope="module")
def reference(tmp_path_factory: pytest.TempPathFactory) -> str:
    return replay(tmp_path_factory.mktemp("uncertainty-replay") / "base.sqlite", "0", False)


@pytest.mark.parametrize("seed", ["0", "1", "42", "random"])
@pytest.mark.parametrize("reverse", [False, True])
def test_seed_order_restart(tmp_path: Path, reference: str, seed: str, reverse: bool) -> None:
    assert replay(tmp_path / "replay.sqlite", seed, reverse) == reference
