"""Shared causal fixture copied into a distinct immutable repository per test."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.uncertainty import (
    ForecastUncertaintyDecomposition,
    UncertaintyEngine,
    UncertaintyRepository,
)
from examples.uncertainty_fixture import UncertaintyFixture, build_fixture


@dataclass(frozen=True)
class Base:
    path: Path
    fixture: UncertaintyFixture


@pytest.fixture(scope="session")
def base(tmp_path_factory: pytest.TempPathFactory) -> Base:
    path = tmp_path_factory.mktemp("uncertainty-session") / "base.sqlite"
    with UncertaintyRepository(path) as repo:
        fixture = build_fixture(repo)
    return Base(path, fixture)


@dataclass
class Case:
    repo: UncertaintyRepository
    fixture: UncertaintyFixture

    @property
    def engine(self) -> UncertaintyEngine:
        return UncertaintyEngine(self.repo)

    def result(self, name: str = "gaussian") -> ForecastUncertaintyDecomposition:
        return self.repo.get(ForecastUncertaintyDecomposition, self.fixture.results(name)[0])


@pytest.fixture
def case(base: Base, tmp_path: Path) -> Iterator[Case]:
    path = tmp_path / "uncertainty.sqlite"
    shutil.copy2(base.path, path)
    with UncertaintyRepository(path) as repo:
        yield Case(repo, base.fixture)
