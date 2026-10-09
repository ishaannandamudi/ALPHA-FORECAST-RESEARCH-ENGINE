"""One complete native seed copied into independent databases for each test."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.multiple_testing import MultipleTestingEngine, MultipleTestingRepository
from examples.multiple_testing_fixture import TestingFixture, build_fixture


@dataclass
class TestingCase:
    repo: MultipleTestingRepository
    fixture: TestingFixture
    engine: MultipleTestingEngine


@pytest.fixture(scope="session")
def testing_seed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, TestingFixture]:
    path = tmp_path_factory.mktemp("multiple-testing-native") / "seed.sqlite"
    with MultipleTestingRepository(path) as repo:
        fixture = build_fixture(repo)
    return path, fixture


@pytest.fixture
def mt_case(tmp_path: Path, testing_seed: tuple[Path, TestingFixture]) -> Iterator[TestingCase]:
    path = tmp_path / "case.sqlite"
    shutil.copyfile(testing_seed[0], path)
    with MultipleTestingRepository(path) as repo:
        yield TestingCase(repo, testing_seed[1], MultipleTestingEngine(repo))


@pytest.fixture(scope="session")
def completed_seed(
    tmp_path_factory: pytest.TempPathFactory, testing_seed: tuple[Path, TestingFixture]
) -> tuple[Path, TestingFixture]:
    from examples.multiple_testing_workflow import complete_fixture

    path = tmp_path_factory.mktemp("completed-testing-native") / "seed.sqlite"
    shutil.copyfile(testing_seed[0], path)
    with MultipleTestingRepository(path) as repo:
        complete_fixture(MultipleTestingEngine(repo), testing_seed[1])
    return path, testing_seed[1]


@pytest.fixture
def completed_case(
    tmp_path: Path, completed_seed: tuple[Path, TestingFixture]
) -> Iterator[TestingCase]:
    path = tmp_path / "completed.sqlite"
    shutil.copyfile(completed_seed[0], path)
    with MultipleTestingRepository(path) as repo:
        yield TestingCase(repo, completed_seed[1], MultipleTestingEngine(repo))
