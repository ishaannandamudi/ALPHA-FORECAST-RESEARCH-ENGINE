"""Full uncertainty/forecast/evaluation replay across seeds, reversed order and restart."""

import os
import subprocess
import sys
from pathlib import Path

from examples.probabilistic_demo import (
    ProbabilityDemoRepository,
    build_probability_demo,
    main,
    probability_bytes,
)

SCRIPT = """
import json
import socket
from pathlib import Path
from tempfile import TemporaryDirectory
from examples.probabilistic_demo import (
    ProbabilityDemoRepository, build_probability_demo, probability_bytes
)
def denied(*args,**kwargs):
    raise AssertionError("network forbidden in probabilistic replay")
for name in ("socket","create_connection","getaddrinfo","gethostbyname",
             "gethostbyname_ex","gethostbyaddr","socketpair"):
    setattr(socket,name,denied)
with TemporaryDirectory() as directory:
    path=Path(directory)/"replay.sqlite"
    with ProbabilityDemoRepository(path) as repo:
        demo=build_probability_demo(repo)
        result=probability_bytes(repo,demo)
    with ProbabilityDemoRepository(path) as repo:
        assert probability_bytes(repo,demo) == result
    print(json.dumps(result,separators=(",",":")))
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


def test_reversed_upstream_train_and_forecast_requests(tmp_path: Path) -> None:
    values = []
    for reverse in (False, True):
        with ProbabilityDemoRepository(tmp_path / f"reverse-{reverse}.sqlite") as repo:
            demo = build_probability_demo(repo, reverse=reverse)
            values.append(probability_bytes(repo, demo))
    assert values[0] == values[1]


def test_offline_demo() -> None:
    main()
