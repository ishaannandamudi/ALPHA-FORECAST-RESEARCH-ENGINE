"""A frozen AFRE-6/7 scaffold copied per test avoids shared mutable evidence."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from afre.calibration import CalibrationEngine, CalibrationFitRun, CalibrationMethod
from examples.calibration_demo import (
    CalibrationDemoRepository,
    CalibrationFixture,
    build_calibration_fixture,
    method_spec,
)


@dataclass(frozen=True)
class CalibrationCase:
    path: Path
    repo: CalibrationDemoRepository
    fixture: CalibrationFixture

    @property
    def engine(self) -> CalibrationEngine:
        return CalibrationEngine(self.repo)

    def fit(self, method: CalibrationMethod = CalibrationMethod.IDENTITY) -> CalibrationFitRun:
        return self.engine.fit(
            method_spec(self.fixture, method), self.fixture.requests, 55, 55, 55
        )


@pytest.fixture(scope="session")
def calibration_base(tmp_path_factory: pytest.TempPathFactory) -> CalibrationCase:
    path = tmp_path_factory.mktemp("calibration-base") / "base.sqlite"
    with CalibrationDemoRepository(path) as repo:
        fixture = build_calibration_fixture(repo)
    return CalibrationCase(path, repo, fixture)


@pytest.fixture
def calibration_case(
    tmp_path: Path, calibration_base: CalibrationCase
) -> Iterator[CalibrationCase]:
    path = tmp_path / "calibration.sqlite"
    shutil.copyfile(calibration_base.path, path)
    with CalibrationDemoRepository(path) as repo:
        yield CalibrationCase(path, repo, calibration_base.fixture)
