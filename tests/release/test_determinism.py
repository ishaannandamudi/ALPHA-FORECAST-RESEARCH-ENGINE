"""Recompute a native corrected chain in fresh processes, with reordered evidence."""

import json
import os
import subprocess
from pathlib import Path


def test_native_chain_seeds_and_reversed_inputs() -> None:
    code = """
import json,sys
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from afre.service import ServiceRepository
from examples.release_workflows import correction_workflow
with TemporaryDirectory() as work:
    with ServiceRepository(Path(work)/'chain.sqlite') as repo:
        value=asdict(correction_workflow(repo, reverse=sys.argv[1]=='reverse'))
        value.pop('timings')
        print(json.dumps(value,sort_keys=True))
"""
    expected: object = None
    for seed, order in (
        ("0", "forward"),
        ("1", "reverse"),
        ("42", "forward"),
        ("random", "reverse"),
    ):
        result = subprocess.run(
            [str(Path(".venv311/bin/python").resolve()), "-c", code, order],
            env=dict(os.environ, PYTHONHASHSEED=seed),
            capture_output=True,
            text=True,
            check=True,
        )
        value = json.loads(result.stdout)
        if expected is None:
            expected = value
        assert value == expected
