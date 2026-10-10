"""Completed AFRE20 decisions and AFRE19 attempts remain frozen monitoring context."""

from pathlib import Path
from unittest.mock import patch

from afre.health import HealthEngine, HealthMetric, HealthRepository, HealthSpec
from afre.selection import SelectionEngine
from examples.health_selection import selected_monitor


def test_selected_model_and_trial_metadata(tmp_path: Path) -> None:
    path = tmp_path / "selection-health.sqlite"
    result, _ = selected_monitor(path)
    with HealthRepository(path) as repo:
        metric = repo.resolve(HealthMetric, result.metric_ids[0])
        assert not metric.truth_ids
        spec = repo.get(HealthSpec, result.spec_id)
        assert len(spec.context_ids) == 3
        with patch.object(
            SelectionEngine, "select", side_effect=AssertionError("monitoring reran selection")
        ):
            assert HealthEngine(repo).evaluate(spec.fingerprint, 120) == result


def test_context_certificate_clock_forgery(tmp_path: Path) -> None:
    from dataclasses import replace

    import pytest

    from afre.schema import ContractError

    path = tmp_path / "context-forgery.sqlite"
    result, _ = selected_monitor(path)
    with HealthRepository(path) as repo:
        spec = repo.get(HealthSpec, result.spec_id)
        first, *rest = spec.context_records
        forged = replace(
            spec, context_records=((first[0], first[1], first[2] - 1, first[3]), *rest)
        )
        with (
            repo.feature_only(),
            repo.transaction(),
            pytest.raises(ContractError, match="clock certificate"),
        ):
            repo.put(forged)
