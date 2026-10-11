"""Session-built frozen producers copied into isolated challenge stores."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.challenger import ChallengeEngine, ChallengeRepository
from examples.challenger_fixture import ChallengeFixture, build_challenge_fixture


@dataclass
class ChallengeCase:
    repo: ChallengeRepository
    engine: ChallengeEngine
    fixture: ChallengeFixture
    path: Path


@pytest.fixture(scope="session")
def challenge_template(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, ChallengeFixture]:
    path = tmp_path_factory.mktemp("challenge-template") / "evidence.sqlite"
    with ChallengeRepository(path) as repo:
        fixture = build_challenge_fixture(repo)
    return path, fixture


@pytest.fixture
def challenge_case(
    tmp_path: Path, challenge_template: tuple[Path, ChallengeFixture]
) -> Iterator[ChallengeCase]:
    source, fixture = challenge_template
    path = tmp_path / "challenge.sqlite"
    shutil.copyfile(source, path)
    with ChallengeRepository(path) as repo:
        yield ChallengeCase(repo, ChallengeEngine(repo), fixture, path)
