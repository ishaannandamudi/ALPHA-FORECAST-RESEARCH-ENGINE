"""Fresh interpreter replay, fixed references and parallel SQLite corrections."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from afre.fusion import (
    ExternalFusionDefinition,
    ExternalFusionOutput,
    FusedForecast,
    FusionEngine,
)
from afre.health import HealthDiagnostic as D
from afre.health import HealthRepository
from afre.serialization import canonical_json
from afre.target_engine.market_data import TargetBar
from examples.health_fixture import health_spec
from tests.health.conftest import HealthCase


def test_frozen_parallel_writer(health_case: HealthCase) -> None:
    c = health_case
    s, rules = health_spec(c.repo, c.fixture, (D.PREDICTION_MEAN, D.MAE))
    c.engine.declare(s, rules)
    expected = c.engine.evaluate(s.fingerprint, 120)

    def writer() -> tuple[str, ...]:
        with HealthRepository(c.path) as repo:
            raw = repo.get(FusedForecast, c.fixture.output_ids[0])
            assert raw.contributions[0].output_id is not None
            original = repo.get(ExternalFusionOutput, raw.contributions[0].output_id)
            corrected = replace(
                original, value=(original.value or 0) + 10.0, revision="health-correction"
            )
            definition = repo.get(ExternalFusionDefinition, original.definition_id)
            f = FusionEngine(repo)
            f.external(definition, (corrected,))
            obs = f.observe(raw.contributions[0].source_id, corrected.fingerprint)
            changed = f.apply(
                raw.artifact_id, raw.sample_id, (obs.fingerprint,), raw.origin.timestamp_ns
            )
            bar_id = repo._connection.execute(
                "SELECT fingerprint FROM target_artifacts WHERE type_name='TargetBar' LIMIT 1"
            ).fetchone()[0]
            bar = repo.get(TargetBar, bar_id)
            rule = replace(rules[0], label="parallel-rule-correction", degraded=99.0)
            with repo.transaction():
                repo.put(replace(bar, close=(bar.close or 0) + 1, predecessor_id=bar_id))
                repo.put(rule)
            return changed.fingerprint, rule.fingerprint

    changed: tuple[str, ...] = ()

    def hook() -> None:
        nonlocal changed
        with ThreadPoolExecutor(max_workers=1) as pool:
            changed = pool.submit(writer).result(timeout=30)

    actual = c.engine.evaluate(s.fingerprint, 120, snapshot_hook=hook)
    assert canonical_json(actual) == canonical_json(expected)
    assert len(changed) == 2
    ref = c.engine.monitor(changed[0])
    assert ref.fingerprint != c.fixture.reference.fingerprint
    assert c.repo.resolve(type(expected), expected.fingerprint) == expected


def test_fixed_reference_decay_trend(health_case: HealthCase) -> None:
    c = health_case
    spec, rules = health_spec(c.repo, c.fixture, (D.PREDICTION_MEAN,), current_start=20)
    c.engine.declare(spec, rules)
    a = c.engine.evaluate(spec.fingerprint, 120)
    later = replace(
        spec,
        current_window=replace(spec.current_window, start_ns=40, end_ns=41),
        current_observation_ids=health_spec(c.repo, c.fixture, (D.PREDICTION_MEAN,))[
            0
        ].current_observation_ids,
    )
    c.engine.declare(later, rules)
    b = c.engine.evaluate(later.fingerprint, 120)
    trend = c.engine.trend((b.metric_ids[0], a.metric_ids[0]), 120)
    assert trend.slope_per_ns == pytest.approx(3 / 20)
    assert trend.increasing_fraction == 1.0
    assert c.engine.trend(tuple(reversed(trend.metric_ids)), 120) == trend
    wrong = replace(
        later, reference_window=replace(later.reference_window, label="reset-baseline")
    )
    c.engine.declare(wrong, rules)
    w = c.engine.evaluate(wrong.fingerprint, 120)
    from afre.schema import ContractError

    with pytest.raises(ContractError, match="baseline reset"):
        c.engine.trend((a.metric_ids[0], w.metric_ids[0]), 120)


@pytest.mark.parametrize("seed", ("0", "1", "42", "random"))
def test_fresh_interpreter_seed_and_reverse(
    tmp_path: Path, health_template: tuple[Path, object], seed: str
) -> None:
    template, _ = health_template

    results = []
    for reverse in ("0", "1"):
        env = {
            **os.environ,
            "PYTHONHASHSEED": seed,
            "PYTHONPATH": str(Path.cwd() / "src") + os.pathsep + str(Path.cwd()),
        }
        run = subprocess.run(
            [
                sys.executable,
                "-m",
                "examples.health_replay",
                str(template),
                str(tmp_path / (seed + reverse + ".sqlite")),
                reverse,
            ],
            capture_output=True,
            text=True,
            check=True,
            env=env,
        )
        results.append(run.stdout)
    assert results[0] == results[1]
    expected = tmp_path.parent / "health-canonical-wire.txt"
    if expected.exists():
        assert expected.read_text() == results[0]
    else:
        expected.write_text(results[0])


def test_trend_preserves_small_nanoseconds_at_large_utc() -> None:
    from afre.health.trends import slope_and_fraction

    epoch = 1700000000000000000
    assert slope_and_fraction((epoch, epoch + 20), (0.0, 3.0)) == pytest.approx((0.15, 1.0))
