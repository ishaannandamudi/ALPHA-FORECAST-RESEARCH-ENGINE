"""One causal fixture copied into independent repositories; offline via root test guard."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.nonlinear import (
    NonlinearEngine,
    NonlinearForecast,
    NonlinearInput,
    NonlinearRepository,
)
from examples.nonlinear_demo import NonlinearFixture, build_fixture


@dataclass(frozen=True)
class Case:
    repo: NonlinearRepository
    path: Path
    fixture: NonlinearFixture

    @property
    def engine(self) -> NonlinearEngine:
        return NonlinearEngine(self.repo)

    @property
    def forecast(self) -> NonlinearForecast:
        return self.repo.get(NonlinearForecast, self.fixture.forecast_ids[0][0])

    @property
    def inputs(self) -> NonlinearInput:
        return self.repo.get(NonlinearInput, self.forecast.input_id)


@pytest.fixture(scope="session")
def nonlinear_base(tmp_path_factory: pytest.TempPathFactory) -> Case:
    path = tmp_path_factory.mktemp("nonlinear-base") / "base.sqlite"
    with NonlinearRepository(path) as repo:
        fixture = build_fixture(repo)
    return Case(repo, path, fixture)


@pytest.fixture
def case(tmp_path: Path, nonlinear_base: Case) -> Iterator[Case]:
    path = tmp_path / "nonlinear.sqlite"
    shutil.copyfile(nonlinear_base.path, path)
    with NonlinearRepository(path) as repo:
        yield Case(repo, path, nonlinear_base.fixture)
