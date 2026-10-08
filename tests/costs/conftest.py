"""One native seed, independent database per regression; no shared mutable research state."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.costs import CostResearchEngine, CostResearchRepository
from examples.costs_fixture import CostFixture, build_fixture


@dataclass
class CostCase:
    repo: CostResearchRepository
    fixture: CostFixture
    engine: CostResearchEngine


@pytest.fixture(scope="session")
def cost_seed(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, CostFixture]:
    path = tmp_path_factory.mktemp("cost-native-seed") / "seed.sqlite"
    with CostResearchRepository(path) as repo:
        fixture = build_fixture(repo)
    return path, fixture


@pytest.fixture
def case(tmp_path: Path, cost_seed: tuple[Path, CostFixture]) -> Iterator[CostCase]:
    path = tmp_path / "case.sqlite"
    shutil.copyfile(cost_seed[0], path)
    with CostResearchRepository(path) as repo:
        yield CostCase(repo, cost_seed[1], CostResearchEngine(repo))
