"""One offline causal repository, copied for isolated mutation and corruption checks."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.orthogonalization import OrthogonalizationEngine, OrthogonalizationRepository
from examples.orthogonalization_fixture import OrthogonalFixture, build_fixture


@dataclass(frozen=True)
class Base:
    path: Path
    fixture: OrthogonalFixture


@pytest.fixture(scope="session")
def base(tmp_path_factory: pytest.TempPathFactory) -> Base:
    path = tmp_path_factory.mktemp("orthogonal-session") / "base.sqlite"
    with OrthogonalizationRepository(path) as repo:
        fixture = build_fixture(repo)
    return Base(path, fixture)


@dataclass
class Case:
    repo: OrthogonalizationRepository
    fixture: OrthogonalFixture

    @property
    def engine(self) -> OrthogonalizationEngine:
        return OrthogonalizationEngine(self.repo)


@pytest.fixture
def case(base: Base, tmp_path: Path) -> Iterator[Case]:
    path = tmp_path / "orthogonal.sqlite"
    shutil.copyfile(base.path, path)
    with OrthogonalizationRepository(path) as repo:
        yield Case(repo, base.fixture)
