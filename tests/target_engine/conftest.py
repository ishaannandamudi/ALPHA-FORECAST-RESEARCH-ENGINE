from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from afre.target_engine import TargetEngine, TargetRepository, TargetSession
from afre.time import DAY_NS, TimeRange
from examples.target_demo import CALENDAR_TARGET, register_sources


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[TargetEngine]:
    with TargetRepository(tmp_path / "targets.sqlite") as repository:
        register_sources(repository)
        calendar = replace(
            CALENDAR_TARGET,
            sessions=(TargetSession("synthetic-session-v1", TimeRange(0, DAY_NS)),),
        )
        with repository.transaction():
            repository.put(calendar)
        result = TargetEngine(repository)
        yield result
