"""Actual 1h/1d target identity, independent sequence fits and forecasts."""

from pathlib import Path

from afre.sequence import SequenceModelSpec, SequenceRepository
from examples.regime_horizon_fixture import DAY, HOUR
from examples.sequence_horizon_fixture import horizon_sequences


def test_hour_day(tmp_path: Path) -> None:
    with SequenceRepository(tmp_path / "horizons.sqlite") as repo:
        rows = horizon_sequences(repo)
        specs = tuple(repo.get(SequenceModelSpec, m.spec_id) for m, _ in rows)
        assert {s.target.horizon.duration_ns for s in specs} == {HOUR, DAY}
        assert specs[0].target != specs[1].target
        assert rows[0][0].fingerprint != rows[1][0].fingerprint
        assert rows[0][1][0].origin == rows[1][1][0].origin
        assert rows[0][1][0].fingerprint != rows[1][1][0].fingerprint
