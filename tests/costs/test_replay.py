"""Eight fresh native builds across four seeds and both insertion orders, offline."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from examples.costs_demo import STEPS


def test_fresh_hash_seed_order_restart_replay(tmp_path: Path) -> None:
    assert len(STEPS) == 40
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
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "examples.costs_replay",
                str(tmp_path / f"{seed}-{order}.sqlite"),
                order,
            ],
            cwd=root,
            env=environment,
            text=True,
            capture_output=True,
            timeout=300,
            check=True,
        )
        digest = process.stdout.strip()
        assert len(digest) == 64
        return digest

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(run, cases))
    assert len(set(results)) == 1, dict(zip(cases, results, strict=True))
