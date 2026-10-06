"""Hash seeds, fresh insertion/request reversal and restart require identical semantic bytes."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.orthogonalization.conftest import Base
from tests.orthogonalization.test_repository import legacy_copy


def replay(base: Base, path: Path, seed: str, reverse: bool) -> str:
    legacy_copy(base, path)
    return subprocess.check_output(
        [
            sys.executable,
            "-m",
            "tests.orthogonalization.replay_worker",
            str(path),
            "reverse" if reverse else "normal",
            base.fixture.spec.fold_id,
            base.fixture.spec.target.fingerprint,
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=dict(os.environ, PYTHONHASHSEED=seed),
        text=True,
        timeout=300,
    )


@pytest.fixture(scope="module")
def reference(base: Base, tmp_path_factory: pytest.TempPathFactory) -> str:
    return replay(base, tmp_path_factory.mktemp("ort-replay") / "base.sqlite", "0", False)


@pytest.mark.parametrize("seed", ["0", "1", "42", "random"])
@pytest.mark.parametrize("reverse", [False, True])
def test_seed_order_restart(
    base: Base, tmp_path: Path, reference: str, seed: str, reverse: bool
) -> None:
    assert replay(base, tmp_path / "replay.sqlite", seed, reverse) == reference
