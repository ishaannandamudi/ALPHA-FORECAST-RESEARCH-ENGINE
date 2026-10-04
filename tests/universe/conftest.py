from collections.abc import Iterator
from pathlib import Path

import pytest

from afre.universe import UniverseRepository
from examples.universe_demo import DemoFixture, populate


@pytest.fixture
def fixture(tmp_path: Path) -> Iterator[DemoFixture]:
    with UniverseRepository(tmp_path / "universe.sqlite") as repository:
        yield populate(repository)
