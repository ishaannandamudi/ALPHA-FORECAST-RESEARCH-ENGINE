"""Hash-seed, reversed-insertion and restart replay of fits/forecasts/evaluations."""

import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from examples.statistical_baselines_demo import DemoRepository, build_demo, main, semantic_bytes

SCRIPT = """
import json
import socket
from pathlib import Path
from tempfile import TemporaryDirectory
from examples.statistical_baselines_demo import DemoRepository, build_demo, semantic_bytes
def denied(*args, **kwargs):
    raise AssertionError("network forbidden in model replay")
for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname",
             "gethostbyname_ex", "gethostbyaddr", "socketpair"):
    setattr(socket, name, denied)
with TemporaryDirectory() as directory:
    path = Path(directory) / "replay.sqlite"
    with DemoRepository(path) as repo:
        demo = build_demo(repo)
        result = semantic_bytes(repo, demo)
    with DemoRepository(path) as repo:
        assert semantic_bytes(repo, demo) == result
    print(json.dumps(result, separators=(",", ":")))
"""


def test_hash_seeds_and_restart() -> None:
    results = []
    for seed in ("0", "1", "42", "random"):
        result = subprocess.run(
            [sys.executable, "-c", SCRIPT],
            env={**os.environ, "PYTHONHASHSEED": seed},
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=True,
        )
        results.append(result.stdout)
    assert len(set(results)) == 1


def test_reversed_upstream_requests_and_prediction_insertion() -> None:
    with TemporaryDirectory() as directory:
        values = []
        for reverse in (False, True):
            with DemoRepository(Path(directory) / f"reverse-{reverse}.sqlite") as repo:
                demo = build_demo(repo, reverse=reverse)
                values.append(semantic_bytes(repo, demo))
        assert values[0] == values[1]


def test_offline_demo() -> None:
    main()
