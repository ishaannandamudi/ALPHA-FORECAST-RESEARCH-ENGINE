"""Reusable committed upstream fixtures, copied before each mutation test."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.research_datasets import DatasetEngine, DatasetRepository, ResearchDatasetManifest
from examples.research_dataset_demo import ResearchFixture, populate


@dataclass(frozen=True)
class Case:
    path: Path
    repository: DatasetRepository
    engine: DatasetEngine
    fixture: ResearchFixture
    dataset: ResearchDatasetManifest


@pytest.fixture(scope="session")
def research_baseline(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, ResearchFixture, ResearchDatasetManifest]:
    path = tmp_path_factory.mktemp("research-baseline") / "baseline.sqlite"
    with DatasetRepository(path) as repository:
        fixture = populate(repository)
        dataset = DatasetEngine(repository).build_dataset(
            fixture.definition, fixture.requests, 100, 100
        )
    return path, fixture, dataset


@pytest.fixture
def case(
    tmp_path: Path, research_baseline: tuple[Path, ResearchFixture, ResearchDatasetManifest]
) -> Iterator[Case]:
    source, fixture, dataset = research_baseline
    path = tmp_path / "research.sqlite"
    shutil.copyfile(source, path)
    with DatasetRepository(path) as repository:
        yield Case(path, repository, DatasetEngine(repository), fixture, dataset)
