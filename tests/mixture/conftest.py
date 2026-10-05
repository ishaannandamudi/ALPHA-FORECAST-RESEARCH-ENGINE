"""One immutable causal native/external baseline copied independently for each test."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.mixture import MixtureEngine, MixtureForecast, MixtureRepository
from afre.research_datasets.samples import ResearchSample
from examples.mixture_demo import MixtureFixture, build_fixture


@dataclass(frozen=True)
class Case:
    repo: MixtureRepository
    path: Path
    fixture: MixtureFixture

    @property
    def engine(self) -> MixtureEngine:
        return MixtureEngine(self.repo)

    @property
    def forecast(self) -> MixtureForecast:
        return self.repo.get(MixtureForecast, self.fixture.forecast_ids[0])

    @property
    def sample(self) -> ResearchSample:
        return self.repo.get(ResearchSample, self.forecast.request.sample_id)


@pytest.fixture(scope="session")
def mixture_base(tmp_path_factory: pytest.TempPathFactory) -> Case:
    path = tmp_path_factory.mktemp("mixture-base") / "base.sqlite"
    with MixtureRepository(path) as repo:
        fixture = build_fixture(repo)
    return Case(repo, path, fixture)


@pytest.fixture
def case(tmp_path: Path, mixture_base: Case) -> Iterator[Case]:
    path = tmp_path / "mixture.sqlite"
    shutil.copyfile(mixture_base.path, path)
    with MixtureRepository(path) as repo:
        yield Case(repo, path, mixture_base.fixture)
