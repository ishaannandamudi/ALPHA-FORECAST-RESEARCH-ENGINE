"""Small local foundation benchmark, with no SLA claim."""

import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.persistence import ArtifactStore
from examples.foundation_demo import build_demo


def main() -> None:
    demo = build_demo()
    count = 100_000
    start = perf_counter()
    for number in range(count):
        replace(demo.features[0], value=number / count)
    construction = perf_counter() - start
    start = perf_counter()
    for _ in range(1000):
        identity = demo.row.dataset.fingerprint
    assert identity == demo.row.dataset.fingerprint
    hashing = perf_counter() - start
    with TemporaryDirectory(prefix="afre-benchmark-") as directory:
        start = perf_counter()
        path = Path(directory) / "research.sqlite"
        with ArtifactStore(path) as store, store.transaction():
            store.put(demo.row.dataset)
        with ArtifactStore(path) as restarted:
            for _ in range(100):
                restarted.get(type(demo.row.dataset), demo.row.dataset.fingerprint)
            assert restarted.audit() == 1
        replay = perf_counter() - start
    print(
        json.dumps(
            {
                "feature_constructions": count,
                "construction_seconds": construction,
                "manifest_hashes": 1000,
                "hash_seconds": hashing,
                "persistence_and_100_reloads_seconds": replay,
            },
            sort_keys=True,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
