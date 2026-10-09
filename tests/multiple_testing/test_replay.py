"""Eight fresh offline builds across seeds, reversed declarations/requests and restart."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from examples.multiple_testing_demo import STEPS


def test_fresh_seed_order_requests_restart_36_steps(tmp_path: Path) -> None:
    assert len(STEPS) == 36
    root = Path(__file__).resolve().parents[2]
    cases = tuple(
        (seed, order) for seed in ("0", "1", "42", "random") for order in ("normal", "reverse")
    )

    def run(case: tuple[str, str]) -> str:
        seed, order = case
        environment = dict(
            os.environ,
            PYTHONHASHSEED=seed,
            PYTHONPATH=str(root / "src") + os.pathsep + str(root),
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "examples.multiple_testing_replay",
                str(tmp_path / f"{seed}-{order}.sqlite"),
                order,
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
            timeout=600,
        )
        digest = result.stdout.strip()
        assert len(digest) == 64
        return digest

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(run, cases))
    assert len(set(results)) == 1, dict(zip(cases, results, strict=True))
