"""One immutable native fixture snapshot; each test gets an isolated store."""

from collections.abc import Iterator
from pathlib import Path
from shutil import copyfile

import pytest

from afre.fusion import FusionRepository
from examples.fusion_fixture import FusionFixture, build_fixture


@pytest.fixture(scope="session")
def fusion_template(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, FusionFixture]:
    path = tmp_path_factory.mktemp("fusion-template") / "template.sqlite"
    with FusionRepository(path) as repo:
        fixture = build_fixture(repo)
    return path, fixture


@pytest.fixture
def fusion_case(
    fusion_template: tuple[Path, FusionFixture], tmp_path: Path
) -> Iterator[tuple[FusionRepository, FusionFixture]]:
    template, fixture = fusion_template
    path = tmp_path / "fusion.sqlite"
    copyfile(template, path)
    with FusionRepository(path) as repo:
        yield repo, fixture
