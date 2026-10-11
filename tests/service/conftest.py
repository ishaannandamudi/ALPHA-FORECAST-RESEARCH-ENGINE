"""Native sources built once, then copied into isolated additive SQLite25 stores."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.service import AFREService, ServiceRepository, SnapshotPublisher
from examples.service_fixture import ServiceFixture, build_fixture


@dataclass
class ServiceCase:
    repo: ServiceRepository
    publisher: SnapshotPublisher
    service: AFREService
    fixture: ServiceFixture
    path: Path


@pytest.fixture(scope="session")
def service_template(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, ServiceFixture]:
    path = tmp_path_factory.mktemp("service-template") / "native.sqlite"
    with ServiceRepository(path) as repo:
        fixture = build_fixture(repo)
    return path, fixture


@pytest.fixture
def service_case(
    tmp_path: Path, service_template: tuple[Path, ServiceFixture]
) -> Iterator[ServiceCase]:
    template, fixture = service_template
    path = tmp_path / "service.sqlite"
    shutil.copyfile(template, path)
    with ServiceRepository(path) as repo:
        yield ServiceCase(repo, SnapshotPublisher(repo), AFREService(repo), fixture, path)
