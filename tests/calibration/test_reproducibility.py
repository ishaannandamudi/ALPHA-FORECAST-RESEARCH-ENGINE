"""Representative fit/application/evaluation bytes across hash seed/order/restart."""

import os
import subprocess
import sys
from pathlib import Path


def test_seed_order_and_restart_replay(tmp_path: Path) -> None:
    results = []
    for seed, order in (
        ("0", "forward"),
        ("1", "forward"),
        ("42", "forward"),
        ("random", "forward"),
        ("0", "reverse"),
    ):
        environment = dict(os.environ, PYTHONHASHSEED=seed)
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.calibration.replay_worker",
                str(tmp_path / f"{seed}-{order}.sqlite"),
                order,
            ],
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        results.append(result.stdout)
    assert all(r == results[0] for r in results)
