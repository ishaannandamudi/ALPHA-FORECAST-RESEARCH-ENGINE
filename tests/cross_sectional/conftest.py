"""Independent copies of a causal multi-security fixture."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.cross_sectional import CrossSectionEngine, CrossSectionRepository
from examples.cross_sectional_demo import CrossSectionFixture, cross_fixture


@dataclass(frozen=True)
class Case:
    path: Path
    repo: CrossSectionRepository
    fixture: CrossSectionFixture

    @property
    def engine(self) -> CrossSectionEngine:
        return CrossSectionEngine(self.repo)


@pytest.fixture(scope="session")
def cross_base(tmp_path_factory: pytest.TempPathFactory) -> Case:
    path = tmp_path_factory.mktemp("cross-section-base") / "base.sqlite"
    with CrossSectionRepository(path) as repo:
        f = cross_fixture(repo)
    return Case(path, repo, f)


@pytest.fixture
def case(tmp_path: Path, cross_base: Case) -> Iterator[Case]:
    path = tmp_path / "research.sqlite"
    shutil.copyfile(cross_base.path, path)
    with CrossSectionRepository(path) as repo:
        yield Case(path, repo, cross_base.fixture)
