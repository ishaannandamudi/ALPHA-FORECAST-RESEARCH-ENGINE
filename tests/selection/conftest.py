"""Frozen native fixtures copied per test, without rebuilding prior phases."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.selection import SearchSpace, SelectionEngine, SelectionRepository
from afre.selection.registry import CandidateRegistrySnapshot
from afre.selection.results import SelectionResult
from examples.selection_fixture import SelectionFixture, family_fixture, small_fixture


@dataclass(frozen=True)
class SelectionCase:
    path: Path
    repository: SelectionRepository
    fixture: SelectionFixture
    result: SelectionResult
    registry: CandidateRegistrySnapshot

    @property
    def space(self) -> SearchSpace:
        return self.fixture.space


@pytest.fixture(scope="session")
def selection_baseline(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, SelectionFixture, SelectionResult, CandidateRegistrySnapshot]:
    path = tmp_path_factory.mktemp("selection-native") / "baseline.sqlite"
    with SelectionRepository(path) as repo:
        fixture = small_fixture(repo)
        result, registry = SelectionEngine(repo).select(fixture.space, 100, 100)
    return path, fixture, result, registry


@pytest.fixture
def case(
    tmp_path: Path,
    selection_baseline: tuple[
        Path, SelectionFixture, SelectionResult, CandidateRegistrySnapshot
    ],
) -> Iterator[SelectionCase]:
    original, fixture, result, registry = selection_baseline
    path = tmp_path / "selection.sqlite"
    shutil.copyfile(original, path)
    with SelectionRepository(path) as repo:
        yield SelectionCase(path, repo, fixture, result, registry)


@pytest.fixture(scope="session")
def selection_families(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, SelectionFixture, SelectionResult, CandidateRegistrySnapshot]:
    path = tmp_path_factory.mktemp("selection-families") / "families.sqlite"
    with SelectionRepository(path) as repo:
        fixture = family_fixture(repo)
        result, registry = SelectionEngine(repo).select(fixture.space, 100, 100)
    return path, fixture, result, registry
