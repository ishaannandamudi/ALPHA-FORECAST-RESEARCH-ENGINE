"""One native offline baseline, copied for isolated AFRE-17 tests."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.invariance import InvarianceEngine, InvarianceRepository
from examples.invariance_fixture import InvarianceFixture, build_fixture


@dataclass(frozen=True)
class Base:
    path: Path
    fixture: InvarianceFixture


@pytest.fixture(scope="session")
def base(tmp_path_factory: pytest.TempPathFactory) -> Base:
    path = tmp_path_factory.mktemp("invariance-session") / "base.sqlite"
    with InvarianceRepository(path) as repo:
        fixture = build_fixture(repo)
    return Base(path, fixture)


@dataclass
class Case:
    repo: InvarianceRepository
    fixture: InvarianceFixture

    @property
    def engine(self) -> InvarianceEngine:
        return InvarianceEngine(self.repo)


@pytest.fixture
def case(base: Base, tmp_path: Path) -> Iterator[Case]:
    path = tmp_path / "invariance.sqlite"
    shutil.copyfile(base.path, path)
    with InvarianceRepository(path) as repo:
        yield Case(repo, base.fixture)
