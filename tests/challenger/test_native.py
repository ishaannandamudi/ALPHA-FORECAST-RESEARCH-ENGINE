"""Actual AFRE families, frozen fusion, native uncertainty and PIT cohorts."""

import shutil
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from afre.challenger import (
    ChallengeDirection,
    ChallengeEngine,
    ChallengeRepository,
    ChallengeStatus,
    CommonMatchedEvidence,
    ParticipantMetricResult,
    PromotionCriterion,
    RollbackAssessment,
    RollbackCriterion,
    RollbackOutcome,
    ShadowForecast,
)
from afre.health import HealthStatus
from afre.serialization import canonical_json
from examples.challenge_native import native_challenge, panel_family
from examples.health_native import NativeHealthFixture, build_native, matching_family


@pytest.fixture(scope="session")
def native_challenge_template(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, NativeHealthFixture]:
    path = tmp_path_factory.mktemp("native-challenge") / "native.sqlite"
    with ChallengeRepository(path) as repo:
        f = build_native(repo)
    return path, f


@pytest.fixture
def native_challenge_case(
    tmp_path: Path, native_challenge_template: tuple[Path, NativeHealthFixture]
) -> Iterator[tuple[ChallengeRepository, NativeHealthFixture]]:
    path, f = native_challenge_template
    copied = tmp_path / "native.sqlite"
    shutil.copyfile(path, copied)
    with ChallengeRepository(copied) as repo:
        yield repo, f


@pytest.mark.parametrize(
    "family",
    (
        "point",
        "gaussian",
        "empirical",
        "calibrated",
        "event",
        "hard-regime",
        "soft-regime",
        "mixture",
        "nonlinear",
        "tree",
        "sequence",
    ),
)
def test_exact_native_families(
    native_challenge_case: tuple[ChallengeRepository, NativeHealthFixture], family: str
) -> None:
    repo, f = native_challenge_case
    native = f.upstream.upstream.upstream
    candidate = matching_family(repo, native.ids(family))
    champion = matching_family(repo, native.ids("gaussian" if family == "point" else "point"))
    before = tuple(canonical_json(repo.get_any(i)) for i in (*champion, *candidate))
    program, evidence = native_challenge(repo, champion, candidate)
    engine = ChallengeEngine(repo)
    engine.evidence(evidence)
    run = engine.evaluate(evidence.fingerprint)
    common = repo.resolve(CommonMatchedEvidence, run.common_id)
    assert common.status is ChallengeStatus.AVAILABLE and common.assignments
    assert all(
        repo.resolve(ShadowForecast, i).source_id in (*champion, *candidate)
        for i in common.shadow_ids
    )
    assert before == tuple(canonical_json(repo.get_any(i)) for i in (*champion, *candidate))
    assert program.fingerprint == run.program_id and run.action == "MANUAL_ONLY"


@pytest.mark.parametrize("kind", ("EVENT", "REGIME", "SECTOR", "UNIVERSE", "CUSTOM"))
def test_native_pit_cohort(
    native_challenge_case: tuple[ChallengeRepository, NativeHealthFixture], kind: str
) -> None:
    from afre.invariance.artifacts import EnvironmentMembership

    repo, f = native_challenge_case
    environment = next(
        d
        for d in f.cohorts.environment_set.definitions
        if d.kind.name == kind
        and (d.membership_kind is None or d.membership_kind.value == "hard")
    )
    memberships = tuple(
        i
        for i in f.cohorts.membership_ids
        if repo.get(EnvironmentMembership, i).environment_id == environment.fingerprint
    )
    native = f.upstream.upstream.upstream
    program, evidence = native_challenge(
        repo,
        matching_family(repo, native.ids("point")),
        matching_family(repo, native.ids("gaussian")),
        environment_id=environment.fingerprint,
        membership_ids=memberships,
    )
    engine = ChallengeEngine(repo)
    engine.evidence(evidence)
    run = engine.evaluate(evidence.fingerprint)
    common = repo.resolve(CommonMatchedEvidence, run.common_id)
    expected = {
        repo.get(EnvironmentMembership, i).sample_id
        for i in memberships
        if repo.get(EnvironmentMembership, i).weight == 1.0
    }
    assert {s for s, _ in common.assignments} <= expected
    assert common.status is ChallengeStatus.AVAILABLE
    assert program.environment_id == environment.fingerprint


def test_native_uncertainty_and_soft_cohort(
    native_challenge_case: tuple[ChallengeRepository, NativeHealthFixture],
) -> None:
    from afre.invariance.artifacts import EnvironmentMembership

    repo, f = native_challenge_case
    native = f.upstream.upstream.upstream
    environment = next(
        d
        for d in f.cohorts.environment_set.definitions
        if d.membership_kind is not None and d.membership_kind.value == "soft"
    )
    memberships = tuple(
        i
        for i in f.cohorts.membership_ids
        if repo.get(EnvironmentMembership, i).environment_id == environment.fingerprint
    )
    program, evidence = native_challenge(
        repo,
        matching_family(repo, native.ids("point")),
        matching_family(repo, native.ids("gaussian")),
        environment_id=environment.fingerprint,
        membership_ids=memberships,
        uncertainty_ids=native.results("gaussian"),
    )
    engine = ChallengeEngine(repo)
    engine.evidence(evidence)
    run = engine.evaluate(evidence.fingerprint)
    assert (
        repo.resolve(CommonMatchedEvidence, run.common_id).status
        is ChallengeStatus.INCOMPARABLE
    )
    assert program.uncertainty_ids


@pytest.mark.parametrize(
    "case",
    (
        "higher",
        "lower",
        "insufficient",
        "incompatible",
        "health-missing",
        "health-allowed",
        "health-disallowed",
    ),
)
def test_explicit_earlier_baseline_rollback(
    native_challenge_case: tuple[ChallengeRepository, NativeHealthFixture], case: str
) -> None:
    repo, f = native_challenge_case
    native = f.upstream.upstream.upstream
    a, b = (
        matching_family(repo, native.ids("point")),
        matching_family(repo, native.ids("gaussian")),
    )
    engine = ChallengeEngine(repo)
    from afre.uncertainty.sources import source_for

    a, b = panel_family(repo, a[0]), panel_family(repo, b[0])

    common_samples = {source_for(repo, i).sample_id for i in a} & {
        source_for(repo, i).sample_id for i in b
    }
    times = sorted(
        {
            source_for(repo, i).origin.timestamp_ns
            for i in a
            if source_for(repo, i).sample_id in common_samples
        }
    )
    assert len(times) >= 2
    first, second = times[:2]
    prior, evidence = native_challenge(
        repo, a, b, start_ns=first, end_ns=first + 1, name="prior"
    )
    engine.evidence(evidence)
    old = engine.evaluate(evidence.fingerprint)
    baseline = next(
        repo.resolve(ParticipantMetricResult, i)
        for i in old.metric_ids
        if repo.get(ParticipantMetricResult, i).participant_id
        == (prior.challenger_ids[0] if case == "incompatible" else prior.champion_id)
    )
    current, new_evidence = native_challenge(
        repo,
        a,
        b,
        start_ns=second,
        end_ns=second + 1,
        name="current",
        declared_ns=120,
        predeclared=False,
    )
    rule = RollbackCriterion(
        "explicit-prior",
        current.requests[0].fingerprint,
        baseline.fingerprint,
        ChallengeDirection.LOWER if case == "lower" else ChallengeDirection.HIGHER,
        0.0,
        2000 if case == "insufficient" else 1,
        120,
        required_health=(
            (HealthStatus.DEGRADED if case == "health-disallowed" else HealthStatus.HEALTHY,)
            if case.startswith("health-")
            else ()
        ),
    )
    current = replace(
        current,
        rollback_criterion_ids=(rule.fingerprint,),
        health_participant_ids=(current.champion_id,) if rule.required_health else (),
    )
    engine.declare(
        current,
        tuple(repo.get(PromotionCriterion, i) for i in current.promotion_criterion_ids),
        (rule,),
    )
    shadows = tuple(repo.get(ShadowForecast, i) for i in new_evidence.shadow_ids)
    new_evidence = replace(
        new_evidence,
        program_id=current.fingerprint,
        shadow_ids=tuple(
            engine.shadow(
                current.fingerprint, s.participant_id, s.source_id, s.computed_ns
            ).fingerprint
            for s in shadows
        ),
    )
    if case in ("health-allowed", "health-disallowed"):
        from afre.challenger import ParticipantReference
        from examples.challenge_context import health_bindings_for

        participants = tuple(
            repo.get(ParticipantReference, i)
            for i in (current.champion_id, *current.challenger_ids)
        )
        outputs = ((current.champion_id, a), (current.challenger_ids[0], b))
        new_evidence = replace(
            new_evidence,
            health_bindings=tuple(
                b
                for b in health_bindings_for(repo, participants, outputs, current)
                if b[0] == current.champion_id
            ),
        )
    engine.evidence(new_evidence)
    run = engine.evaluate(new_evidence.fingerprint)
    assessment = repo.resolve(RollbackAssessment, run.rollback_ids[0])
    metric = repo.resolve(ParticipantMetricResult, assessment.current_metric_id)
    assert assessment.action == "MANUAL_ONLY"
    if case == "incompatible":
        assert assessment.outcome is RollbackOutcome.INCOMPARABLE
    elif case == "insufficient":
        assert assessment.outcome is RollbackOutcome.INSUFFICIENT_DATA
    elif case == "health-missing":
        assert assessment.outcome is RollbackOutcome.INCOMPARABLE
    elif case == "health-disallowed":
        assert assessment.outcome is RollbackOutcome.ROLLBACK_NOT_ELIGIBLE
    else:
        assert baseline.value is not None and metric.value is not None
        expected = (
            baseline.value - metric.value if case == "lower" else metric.value - baseline.value
        )
        assert assessment.deterioration == pytest.approx(expected)
        assert assessment.outcome is (
            RollbackOutcome.ROLLBACK_ELIGIBLE
            if expected >= 0
            else RollbackOutcome.ROLLBACK_NOT_ELIGIBLE
        )
    assert repo.resolve(type(old), old.fingerprint) == old
    if case == "higher":
        from afre.schema import ContractError

        repo._connection.execute("DROP TRIGGER immutable_ch_artifacts_update")
        repo._connection.execute(
            "UPDATE ch_artifacts SET payload='{}' WHERE fingerprint=?",
            (assessment.fingerprint,),
        )
        with pytest.raises(ContractError):
            repo.get(RollbackAssessment, assessment.fingerprint)


def test_actual_hour_day_identities(tmp_path: Path) -> None:
    from examples.challenge_horizons import horizon_challenges
    from examples.regime_horizon_fixture import DAY, HOUR

    with ChallengeRepository(tmp_path / "hour-day.sqlite") as repo:
        results = horizon_challenges(repo)
        assert {duration for duration, _ in results} == {HOUR, DAY}
        assert len({run.program_id for _, run in results}) == 2
        assert all(
            repo.resolve(CommonMatchedEvidence, run.common_id).status
            is ChallengeStatus.AVAILABLE
            for _, run in results
        )


def test_compatible_orthogonal_signals_and_unsupported_point_units(
    native_challenge_case: tuple[ChallengeRepository, NativeHealthFixture],
) -> None:
    from unittest.mock import patch

    from afre.challenger import ChallengeMetric
    from afre.orthogonalization import OrthogonalizationEngine
    from afre.research_datasets.schema import Partition
    from examples.orthogonalization_fixture import build_rows

    repo, fixture = native_challenge_case
    native = fixture.upstream.upstream
    # Fixture setup freezes a distinct native projection before designation.
    spec, rows = build_rows(repo, native.spec.fold_id, native.spec.target, 40, tag="challenger")
    orth = OrthogonalizationEngine(repo)
    projected = orth.fit(
        spec, tuple(r.fingerprint for r in rows if r.partition is Partition.TRAIN), 40
    )
    right = tuple(
        orth.residual(projected.fingerprint, r.fingerprint, r.origin.timestamp_ns).fingerprint
        for r in rows
        if r.partition is Partition.VALIDATION
    )
    left = native.residual_ids(Partition.VALIDATION)
    for metric in (ChallengeMetric.IC, ChallengeMetric.MAE, ChallengeMetric.CRPS):
        with patch.object(
            OrthogonalizationEngine, "fit", side_effect=AssertionError("shadow refit")
        ):
            program, evidence = native_challenge(repo, left, right, metric=metric)
            engine = ChallengeEngine(repo)
            engine.evidence(evidence)
            run = engine.evaluate(evidence.fingerprint)
        results = tuple(repo.resolve(ParticipantMetricResult, i) for i in run.metric_ids)
        assert all(
            m.status
            is (
                ChallengeStatus.AVAILABLE
                if metric is ChallengeMetric.IC
                else ChallengeStatus.INCOMPARABLE
            )
            for m in results
        )
        assert program.unit == "synthetic-unit"
        assert all(repo.get(ShadowForecast, i).law_id is None for i in evidence.shadow_ids)


@pytest.mark.parametrize("family", ("point", "empirical", "mixture"))
def test_native_law_support_without_fabricated_metrics(
    native_challenge_case: tuple[ChallengeRepository, NativeHealthFixture], family: str
) -> None:
    from math import fsum

    from afre.challenger import ChallengeMetric
    from afre.health.probabilities import law_for
    from afre.probabilistic.artifacts import DistributionParameters
    from afre.target_engine.models import TargetVintage

    repo, f = native_challenge_case
    native = f.upstream.upstream.upstream
    left = matching_family(repo, native.ids("gaussian"))
    right = matching_family(repo, native.ids(family))
    for metric in (
        ChallengeMetric.CRPS,
        ChallengeMetric.NLL,
        ChallengeMetric.BRIER,
        ChallengeMetric.PINBALL,
        ChallengeMetric.COVERAGE,
        ChallengeMetric.SHARPNESS,
    ):
        program, evidence = native_challenge(repo, left, right, metric=metric)
        engine = ChallengeEngine(repo)
        engine.evidence(evidence)
        run = engine.evaluate(evidence.fingerprint)
        result = next(
            repo.get(ParticipantMetricResult, i)
            for i in run.metric_ids
            if repo.get(ParticipantMetricResult, i).participant_id == program.challenger_ids[0]
        )
        if family == "point" or (
            family == "mixture"
            and metric
            in (ChallengeMetric.PINBALL, ChallengeMetric.COVERAGE, ChallengeMetric.SHARPNESS)
        ):
            assert result.status is ChallengeStatus.UNAVAILABLE and result.value is None
        if family == "empirical" and metric is ChallengeMetric.CRPS:
            common = repo.get(CommonMatchedEvidence, run.common_id)
            truth = dict(common.assignments)
            errors = []
            for identity in common.shadow_ids:
                shadow = repo.get(ShadowForecast, identity)
                if shadow.participant_id != result.participant_id:
                    continue
                law, _ = law_for(repo, shadow.source_id)
                assert isinstance(law, DistributionParameters)
                y = repo.get(TargetVintage, truth[shadow.sample_id]).value
                assert y is not None
                draws = tuple(law.location + residual for residual in law.samples)
                assert draws
                n = len(draws)
                errors.append(
                    fsum(abs(x - y) for x in draws) / n
                    - fsum(abs(a - b) for a in draws for b in draws) / (2 * n * n)
                )
            assert result.value == pytest.approx(fsum(errors) / len(errors), abs=1e-12)


def test_exact_probabilistic_model_anchor(
    native_challenge_case: tuple[ChallengeRepository, NativeHealthFixture],
) -> None:
    from afre.challenger import ParticipantReference, ParticipantRole
    from afre.probabilistic.artifacts import ProbabilisticForecast

    repo, f = native_challenge_case
    output = matching_family(repo, f.upstream.upstream.upstream.ids("gaussian"))[0]
    raw = repo.get(ProbabilisticForecast, output)
    participant = ChallengeEngine(repo).participant(
        "explicit-native-probabilistic-model",
        ParticipantRole.CHALLENGER,
        raw.model_artifact_id,
        anchor_id=output,
    )
    assert participant.reference.producer_id == raw.model_artifact_id
    assert participant.reference.anchor_output_id == output
    assert repo.resolve(ParticipantReference, participant.fingerprint) == participant
