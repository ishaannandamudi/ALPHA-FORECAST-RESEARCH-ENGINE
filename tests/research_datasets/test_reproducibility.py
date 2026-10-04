"""Byte-identical process/hash-seed replay with network disabled in each child."""

import os
import subprocess
import sys
from pathlib import Path

from afre.research_datasets import DatasetRepository, ResearchSplit
from examples.research_dataset_demo import main, split_definition
from tests.research_datasets.conftest import Case

SCRIPT = """
import json
import socket
from pathlib import Path
from tempfile import TemporaryDirectory
from afre.research_datasets import DatasetRepository, DatasetEngine
from afre.serialization import canonical_json
from examples.research_dataset_demo import populate, split_definition

def denied(*args, **kwargs):
    raise AssertionError("network disabled in replay")
for name in ("socket", "create_connection", "getaddrinfo", "gethostbyname",
             "gethostbyname_ex", "gethostbyaddr", "socketpair"):
    setattr(socket, name, denied)
with TemporaryDirectory() as directory:
    path = Path(directory) / "replay.sqlite"
    with DatasetRepository(path) as repo:
        fixture = populate(repo)
        engine = DatasetEngine(repo)
        dataset = engine.build_dataset(fixture.definition, fixture.requests, 100, 100)
        split = engine.build_split(dataset.fingerprint, split_definition(fixture))
        states = tuple(engine.fit_preprocessing(f, fixture.preprocessing)
                       for f in split.fold_ids)
        exported = engine.export_rows(dataset.fingerprint, 100)
        audits = [canonical_json(engine.audit_fold(f)) for f in split.fold_ids]
        value = [canonical_json(dataset), canonical_json(split), exported,
                 [canonical_json(s) for s in states], audits]
    with DatasetRepository(path) as repo:
        assert DatasetEngine(repo).export_rows(dataset.fingerprint, 100) == value[2]
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
"""


def test_hash_seeds_and_restart() -> None:
    outputs = []
    for seed in ("0", "1", "42", "random"):
        result = subprocess.run(
            [sys.executable, "-c", SCRIPT],
            env={**os.environ, "PYTHONHASHSEED": seed},
            cwd=Path(__file__).resolve().parents[2],
            text=True,
            capture_output=True,
            check=True,
        )
        outputs.append(result.stdout)
    assert len(set(outputs)) == 1


def test_split_restart_and_explicit_determinism(case: Case) -> None:
    split = case.engine.build_split(case.dataset.fingerprint, split_definition(case.fixture))
    with DatasetRepository(case.path) as restarted:
        assert restarted.get(ResearchSplit, split.fingerprint) == split
        assert restarted.dataset_samples(
            case.dataset.fingerprint
        ) == case.engine.dataset_samples(case.dataset.fingerprint)
        restarted.audit()


def test_demo(capsys: object) -> None:
    main()
