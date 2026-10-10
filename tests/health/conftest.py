"""Session-built native evidence copied into isolated health test stores."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.health import HealthEngine, HealthRepository
from examples.health_fixture import HealthFixture, build_health_fixture
from examples.health_native import NativeHealthFixture


@dataclass
class HealthCase:
    repo: HealthRepository
    engine: HealthEngine
    fixture: HealthFixture
    path: Path


@pytest.fixture(scope="session")
def health_template(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, HealthFixture]:
    path = tmp_path_factory.mktemp("health-template") / "evidence.sqlite"
    with HealthRepository(path) as repo:
        fixture = build_health_fixture(repo)
    return path, fixture


@pytest.fixture
def health_case(
    tmp_path: Path, health_template: tuple[Path, HealthFixture]
) -> Iterator[HealthCase]:
    source, fixture = health_template
    path = tmp_path / "health.sqlite"
    shutil.copyfile(source, path)
    with HealthRepository(path) as repo:
        yield HealthCase(repo, HealthEngine(repo), fixture, path)


@pytest.fixture(scope="session")
def native_health_template(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, "NativeHealthFixture"]:
    from examples.health_native import build_native

    path = tmp_path_factory.mktemp("health-native-template") / "evidence.sqlite"
    with HealthRepository(path) as repo:
        fixture = build_native(repo)
    return path, fixture


@pytest.fixture
def native_health_case(
    tmp_path: Path, native_health_template: tuple[Path, "NativeHealthFixture"]
) -> Iterator[tuple[HealthRepository, "NativeHealthFixture"]]:
    source, fixture = native_health_template
    path = tmp_path / "native-health.sqlite"
    shutil.copyfile(source, path)
    with HealthRepository(path) as repo:
        yield repo, fixture
