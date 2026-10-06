"""Actual elapsed-horizon identity and explicit incompatible upstream calibration."""

from pathlib import Path

import pytest

from afre.calibration import CalibrationEngine
from afre.nonlinear import NonlinearCalibrationStatus, NonlinearModelSpec, NonlinearRepository
from afre.schema import ContractError
from examples.nonlinear_horizon_fixture import horizon_interactions
from examples.regime_horizon_fixture import DAY, HOUR
from tests.nonlinear.conftest import Case


def test_actual_hour_and_day(tmp_path: Path) -> None:
    with NonlinearRepository(tmp_path / "horizons.sqlite") as repo:
        rows = horizon_interactions(repo)
        assert len(rows) == 2
        specs = tuple(repo.get(NonlinearModelSpec, m.spec_id) for m, _ in rows)
        assert {s.target.horizon.duration_ns for s in specs} == {HOUR, DAY}
        assert specs[0].target != specs[1].target
        assert rows[0][0].fingerprint != rows[1][0].fingerprint
        assert rows[0][1][0].origin == rows[1][1][0].origin
        assert rows[0][1][0].fingerprint != rows[1][1][0].fingerprint


def test_upstream_calibrator_incompatible(case: Case) -> None:
    identity = case.repo._connection.execute(
        "SELECT fingerprint FROM c_artifacts WHERE type_name='CalibrationState' LIMIT 1"
    ).fetchone()[0]
    result = case.engine.assess_calibration(
        case.forecast.fingerprint, case.fixture.forecast_ids[0], 100, proposed_state_id=identity
    )
    assert result.status is NonlinearCalibrationStatus.INCOMPATIBLE
    # AFRE-7 application accepts exact AFRE-6 raw forecasts; nonlinear output cannot masquerade.
    with pytest.raises(ContractError):
        CalibrationEngine(case.repo).apply(identity, case.forecast.fingerprint, 60)
