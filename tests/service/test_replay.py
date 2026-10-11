"""Canonical replay across restarts, reversed requests and concurrent append."""

import os
import subprocess
from dataclasses import replace
from pathlib import Path

from afre.service import (
    AFREService,
    RegistryQuery,
    ServiceRepository,
    SnapshotPublication,
    SnapshotPublisher,
    canonical_json,
)
from tests.service.conftest import ServiceCase


def test_restart_seeds_and_order(service_case: ServiceCase, tmp_path: Path) -> None:
    c = service_case
    sources = c.fixture.ids("point")[:2]
    snapshots = tuple(
        c.publisher.publish(SnapshotPublication(i, "frozen", 120)) for i in sources
    )
    catalog = c.publisher.catalog("frozen", tuple(s.fingerprint for s in snapshots), 120)
    query = RegistryQuery(catalog.fingerprint)
    expected = canonical_json(c.service.list_registry_entries(query))
    assert (
        c.publisher.catalog("frozen", tuple(s.fingerprint for s in reversed(snapshots)), 120)
        == catalog
    )
    replay = tmp_path / "replay.sqlite"
    # Backup covers uncheckpointed WAL without writing anything in the consumer façade.
    with ServiceRepository(replay) as copy:
        c.repo._connection.backup(copy._connection)
    with ServiceRepository(replay) as reopened:
        assert canonical_json(AFREService(reopened).list_registry_entries(query)) == expected
        for s in reversed(snapshots):
            assert SnapshotPublisher(reopened).publish(s.publication) == s
            assert AFREService(reopened).get_snapshot(s.fingerprint).value == s
    code = (
        "from afre.service import *; import sys; "
        "v=deserialize(sys.stdin.read()); print(canonical_json(v))"
    )
    for seed in ("0", "1", "42", "random"):
        env = dict(
            os.environ,
            PYTHONHASHSEED=seed,
            PYTHONPATH="src:." + os.pathsep + os.environ.get("PYTHONPATH", ""),
        )
        result = subprocess.run(
            [str(Path(".venv311/bin/python").resolve()), "-c", code],
            input=expected,
            text=True,
            env=env,
            capture_output=True,
            check=True,
        )
        assert result.stdout.strip() == expected


def test_concurrent_publication_isolation(service_case: ServiceCase) -> None:
    c = service_case
    s = c.publisher.publish(SnapshotPublication(c.fixture.ids("point")[0], "frozen", 120))
    catalog = c.publisher.catalog("frozen", (s.fingerprint,), 120)
    query = RegistryQuery(catalog.fingerprint, page_size=1)
    before = canonical_json(c.service.list_registry_entries(query))
    with ServiceRepository(c.path) as writer:
        with c.repo.read_snapshot():
            first = c.service.get_snapshot(s.fingerprint)
            new = SnapshotPublisher(writer).publish(
                replace(s.publication, publication_version="new")
            )
            SnapshotPublisher(writer).catalog(
                "new-catalog", (s.fingerprint, new.fingerprint), 120
            )
            assert c.service.get_snapshot(s.fingerprint) == first
            assert canonical_json(c.service.list_registry_entries(query)) == before
        assert c.service.get_snapshot(new.fingerprint).value == new
    assert canonical_json(c.service.list_registry_entries(query)) == before


def test_reversed_publications(service_case: ServiceCase, tmp_path: Path) -> None:
    c = service_case
    reverse_path = tmp_path / "reverse.sqlite"
    with ServiceRepository(reverse_path) as reverse:
        c.repo._connection.backup(reverse._connection)
    requests = tuple(SnapshotPublication(i, "same", 120) for i in c.fixture.ids("point")[:2])
    forward = tuple(c.publisher.publish(r) for r in requests)
    with ServiceRepository(reverse_path) as reverse:
        publisher = SnapshotPublisher(reverse)
        backward = tuple(publisher.publish(r) for r in reversed(requests))
        assert {canonical_json(s) for s in forward} == {canonical_json(s) for s in backward}
        one = c.publisher.catalog("canonical", tuple(s.fingerprint for s in forward), 120)
        two = publisher.catalog("canonical", tuple(s.fingerprint for s in backward), 120)
        assert canonical_json(one) == canonical_json(two)
