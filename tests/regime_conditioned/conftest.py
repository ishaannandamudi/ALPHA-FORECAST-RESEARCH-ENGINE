"""Independent per-test copies of immutable hard/soft synthetic research."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.regime_conditioned import RegimeEngine, RegimeRepository
from examples.regime_conditioned_demo import RegimeFixture, build_fixture


@dataclass(frozen=True)
class Case:
    repo: RegimeRepository
    path: Path
    hard: RegimeFixture
    soft: RegimeFixture

    @property
    def engine(self) -> RegimeEngine:
        return RegimeEngine(self.repo)


@pytest.fixture(scope="session")
def regime_base(tmp_path_factory: pytest.TempPathFactory) -> Case:
    path = tmp_path_factory.mktemp("regime-base") / "base.sqlite"
    with RegimeRepository(path) as repo:
        hard = build_fixture(repo)
        soft = build_fixture(repo, upstream=hard.upstream, soft=True)
    return Case(repo, path, hard, soft)


@pytest.fixture
def case(tmp_path: Path, regime_base: Case) -> Iterator[Case]:
    path = tmp_path / "research.sqlite"
    shutil.copyfile(regime_base.path, path)
    with RegimeRepository(path) as repo:
        yield Case(repo, path, regime_base.hard, regime_base.soft)
