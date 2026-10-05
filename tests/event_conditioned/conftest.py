"""Independent SQLite copies of exact causal event evidence."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.event_conditioned import EventEngine, EventRepository
from examples.event_conditioned_demo import EventFixture, build_fixture


@dataclass(frozen=True)
class Case:
    repo: EventRepository
    path: Path
    fixture: EventFixture

    @property
    def engine(self) -> EventEngine:
        return EventEngine(self.repo)


@pytest.fixture(scope="session")
def event_base(tmp_path_factory: pytest.TempPathFactory) -> Case:
    path = tmp_path_factory.mktemp("event-base") / "base.sqlite"
    with EventRepository(path) as repo:
        f = build_fixture(repo)
    return Case(repo, path, f)


@pytest.fixture
def case(tmp_path: Path, event_base: Case) -> Iterator[Case]:
    path = tmp_path / "research.sqlite"
    shutil.copyfile(event_base.path, path)
    with EventRepository(path) as repo:
        yield Case(repo, path, event_base.fixture)
