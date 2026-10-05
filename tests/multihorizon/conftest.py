"""Independent SQLite copies of an immutable two-horizon scaffold."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.multihorizon import MultiHorizonEngine, MultiHorizonRepository
from examples.multihorizon_demo import MultiHorizonFixture, build_fixture


@dataclass(frozen=True)
class Case:
    path: Path
    repo: MultiHorizonRepository
    fixture: MultiHorizonFixture

    @property
    def engine(self) -> MultiHorizonEngine:
        return MultiHorizonEngine(self.repo)


@pytest.fixture(scope="session")
def multihorizon_base(tmp_path_factory: pytest.TempPathFactory) -> Case:
    path = tmp_path_factory.mktemp("multi-horizon-base") / "base.sqlite"
    with MultiHorizonRepository(path) as repo:
        fixture = build_fixture(repo)
    return Case(path, repo, fixture)


@pytest.fixture
def case(tmp_path: Path, multihorizon_base: Case) -> Iterator[Case]:
    path = tmp_path / "research.sqlite"
    shutil.copyfile(multihorizon_base.path, path)
    with MultiHorizonRepository(path) as repo:
        yield Case(path, repo, multihorizon_base.fixture)
