"""Explicit status, target protection, immutable histories and TEST boundaries."""

from dataclasses import replace
from pathlib import Path
from typing import TypeVar
from unittest.mock import patch

import pytest

from afre.health import (
    HealthDiagnostic as D,
)
from afre.health import (
    HealthIntersection,
    HealthMetric,
    HealthObservation,
    HealthPairKey,
    HealthRepository,
    HealthStatus,
)
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.statistical_models.evaluation import test_record as native_test_record
from afre.target_engine.models import TargetVintage
from examples.health_fixture import health_spec
from tests.health.conftest import HealthCase

A = TypeVar("A", bound=Artifact)


def test_target_free_even_warm_caches(health_case: HealthCase) -> None:
    c = health_case
    s, r = health_spec(c.repo, c.fixture, (D.PREDICTION_MEAN, D.PREDICTION_KS))
    c.engine.declare(s, r)
    get = c.repo.get

    def deny(cls: type[A], identity: str) -> A:
        if cls is TargetVintage:
            raise AssertionError("held-out or TRAIN target read")
        return get(cls, identity)

    with patch.object(c.repo, "get", deny):
        out = c.engine.evaluate(s.fingerprint, 120)
    assert out.status is HealthStatus.DEGRADED
    with c.repo.read_snapshot(), c.repo.validation_cache():
        sample = c.repo.partition_samples(c.fixture.upstream.spec.fold_id, Partition.TRAIN)[0]
        assert sample.target_id is not None
        c.repo.resolve(TargetVintage, sample.target_id)
        with c.repo.feature_only(), pytest.raises(ContractError, match="target-free"):
            c.repo.get_any(sample.target_id)


def test_no_default_rule_and_support(health_case: HealthCase) -> None:
    c = health_case
    s, _ = health_spec(c.repo, c.fixture, (D.PREDICTION_MEAN,))
    s = replace(s, rule_bindings=())
    c.engine.declare(s)
    out = c.engine.evaluate(s.fingerprint, 120)
    m = c.repo.resolve(HealthMetric, out.metric_ids[0])
    assert m.status is HealthStatus.UNAVAILABLE and m.delta == 3.0
    s, r = health_spec(c.repo, c.fixture, (D.PREDICTION_MEAN,), minimum=4)
    c.engine.declare(s, r)
    out = c.engine.evaluate(s.fingerprint, 120)
    assert out.status is HealthStatus.INSUFFICIENT_DATA


@pytest.mark.parametrize(
    "intersection",
    [HealthIntersection.COMMON_INTERSECTION, HealthIntersection.PAIRWISE_INTERSECTION],
)
def test_explicit_intersection_keys(
    health_case: HealthCase, intersection: HealthIntersection
) -> None:
    c = health_case
    s, r = health_spec(c.repo, c.fixture, (D.PREDICTION_MEAN,))
    s = replace(s, intersection=intersection)
    c.engine.declare(s, r)
    assert c.engine.evaluate(s.fingerprint, 120).status is HealthStatus.INSUFFICIENT_DATA
    s = replace(s, pair_key=HealthPairKey.SECURITY)
    c.engine.declare(s)
    assert c.engine.evaluate(s.fingerprint, 120).status is HealthStatus.DEGRADED


def test_late_truth_excluded(health_case: HealthCase) -> None:
    c = health_case
    s, r = health_spec(c.repo, c.fixture, (D.MAE,), cutoff_ns=41)
    c.engine.declare(s, r)
    out = c.engine.evaluate(s.fingerprint, 120)
    m = c.repo.resolve(HealthMetric, out.metric_ids[0])
    assert m.current_count == 0 and m.status is HealthStatus.INSUFFICIENT_DATA
    assert any("truth-unavailable" in reason for _, reason in m.exclusions)


def test_native_test_seal_and_threshold_isolation(health_case: HealthCase) -> None:
    c = health_case
    s, r = health_spec(c.repo, c.fixture, (D.MAE,), current_start=70)
    c.engine.declare(s, r)
    with pytest.raises(ContractError, match="sealed"):
        c.engine.evaluate(s.fingerprint, 120)
    seal = native_test_record(
        c.repo, c.fixture.upstream.spec.fold_id, "health-test", "descriptive-frozen-health", 120
    )
    c.engine._publish((seal,))
    s = replace(s, test_evaluation_id=seal.fingerprint)
    c.engine.declare(s)
    before = tuple(canonical_json(rule) for rule in r)
    out = c.engine.evaluate(s.fingerprint, 120)
    assert out.status is HealthStatus.DEGRADED and before == tuple(
        canonical_json(rule) for rule in r
    )
    with pytest.raises(ContractError):
        replace(s, declared_ns=71)


def test_history_recovery_and_restart(health_case: HealthCase, tmp_path: Path) -> None:
    c = health_case
    s, r = health_spec(c.repo, c.fixture, (D.PREDICTION_MEAN,))
    c.engine.declare(s, r)
    old = c.engine.evaluate(s.fingerprint, 120)
    healthy = replace(
        s,
        current_window=replace(s.current_window, start_ns=20, end_ns=21),
        current_observation_ids=tuple(
            i
            for i in c.fixture.observation_ids
            if c.repo.get(HealthObservation, i).valid_ns == 20
        ),
    )
    c.engine.declare(healthy)
    new = c.engine.evaluate(healthy.fingerprint, 120)
    assert new.status is HealthStatus.HEALTHY
    assert c.engine.evaluate(s.fingerprint, 120) == old
    assert {a.fingerprint for a in c.engine.history(s.reference_id)} == {
        old.fingerprint,
        new.fingerprint,
    }
    audit = c.engine.audit(old.fingerprint)
    assert len(audit.node_ids) > 100
    with HealthRepository(c.path) as repo:
        assert canonical_json(repo.resolve(type(old), old.fingerprint)) == canonical_json(old)
    assert "NONE" in old.action


@pytest.mark.parametrize("access", ("get", "resolve", "get_any"))
def test_target_guard_before_native_cache(health_case: HealthCase, access: str) -> None:
    c = health_case
    from afre.research_datasets.samples import ResearchSample

    sample = c.repo.get(ResearchSample, c.fixture.upstream.validation[0])
    assert sample.target_id is not None
    with c.repo.read_snapshot(), c.repo.validation_cache():
        c.repo.resolve(TargetVintage, sample.target_id)
        with c.repo.feature_only(), pytest.raises(ContractError, match="target-free"):
            if access == "get_any":
                c.repo.get_any(sample.target_id)
            else:
                getattr(c.repo, access)(TargetVintage, sample.target_id)


def test_snapshot_cannot_backdate_construction(health_case: HealthCase) -> None:
    c = health_case
    s, r = health_spec(c.repo, c.fixture, (D.PREDICTION_MEAN,), cutoff_ns=50)
    c.engine.declare(s, r)
    with pytest.raises(ContractError, match="construction"):
        c.engine.evaluate(s.fingerprint, 50)
    with pytest.raises(ContractError, match="backdated"):
        c.engine.evaluate(s.fingerprint, 49)
