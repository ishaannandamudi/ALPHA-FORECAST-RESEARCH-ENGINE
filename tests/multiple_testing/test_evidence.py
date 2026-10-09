"""Complete/interim state, unsupported inference, exact effects and missing slots."""

from dataclasses import replace

import pytest

from afre.multiple_testing import (
    AdaptiveTrialStatus,
    AdjustedHypothesisResult,
    CorrectionMethod,
    DependenceAssumption,
    EffectSizeResult,
    EvidenceState,
    FamilyAnalysisSpec,
    FamilyCompleteness,
    HypothesisDefinition,
    HypothesisFamily,
    RawTestMethod,
    ResearchMetric,
)
from afre.multiple_testing.raw_tests import raw_results_for
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.target_engine.models import TargetVintage
from examples.multiple_testing_fixture import declare_plan
from tests.multiple_testing.conftest import TestingCase as MTCase
from tests.multiple_testing.helpers import analyses, one_family, trial


@pytest.mark.parametrize(
    "state", [FamilyCompleteness.OPEN, FamilyCompleteness.PARTIAL, FamilyCompleteness.INVALID]
)
def test_missing_slots_never_final(mt_case: MTCase, state: FamilyCompleteness) -> None:
    p = mt_case.fixture.plan("phase-5")
    t = mt_case.engine.complete(p.fingerprint, mt_case.fixture.family.fingerprint, 100, 100)
    output = mt_case.engine.analyze(
        mt_case.fixture.family.fingerprint, (t.fingerprint,), state, 100, 100
    )
    for a in output:
        assert a.missing_count == len(mt_case.fixture.plans) - 1
        assert a.state in (EvidenceState.INTERIM, EvidenceState.INCOMPATIBLE)
        rows = tuple(mt_case.repo.resolve(AdjustedHypothesisResult, i) for i in a.adjusted_ids)
        assert all(
            r.reject is None and r.family_size == len(mt_case.fixture.plans) for r in rows
        )
        missing = tuple(r for r in rows if r.trial_id is None)
        assert all(r.adjusted_value is None and r.raw_p_value is None for r in missing)


def test_complete_cannot_omit_attempt(mt_case: MTCase) -> None:
    p = mt_case.fixture.plan("phase-5")
    t = mt_case.engine.complete(p.fingerprint, mt_case.fixture.family.fingerprint, 100, 100)
    with pytest.raises(ContractError, match="omit"):
        mt_case.engine.analyze(
            mt_case.fixture.family.fingerprint,
            (t.fingerprint,),
            FamilyCompleteness.COMPLETE,
            100,
            100,
        )


@pytest.mark.parametrize(
    "dependence", [DependenceAssumption.ARBITRARY, DependenceAssumption.UNKNOWN]
)
def test_bh_dependence_explicit(mt_case: MTCase, dependence: DependenceAssumption) -> None:
    p = mt_case.fixture.plan("phase-5")
    f = mt_case.engine.family(
        replace(mt_case.fixture.family, plan_ids=(p.fingerprint,), dependence=dependence)
    )
    t = mt_case.engine.complete(p.fingerprint, f.fingerprint, 100, 100)
    results = mt_case.engine.analyze(
        f.fingerprint, (t.fingerprint,), FamilyCompleteness.COMPLETE, 100, 100
    )
    for result in results:
        method = mt_case.repo.resolve(FamilyAnalysisSpec, result.spec_id).correction
        assert (result.state is EvidenceState.UNSUPPORTED) == (
            method is CorrectionMethod.BENJAMINI_HOCHBERG
        )


@pytest.mark.parametrize(
    "key,state",
    [
        ("failed", EvidenceState.INSUFFICIENT),
        ("unavailable", EvidenceState.INSUFFICIENT),
        ("unsupported", EvidenceState.UNSUPPORTED),
    ],
)
def test_unsuccessful_attempts_visible(
    completed_case: MTCase, key: str, state: EvidenceState
) -> None:
    t = trial(completed_case, key)
    p, e = raw_results_for(completed_case.repo, t.fingerprint, t.completed_ns)
    assert p.state is state and p.raw_p_value is None
    assert (e.estimate is None) == (key != "unsupported")
    with completed_case.repo.read_snapshot(), completed_case.repo.validation_cache():
        assert all(
            any(
                completed_case.repo.resolve(AdjustedHypothesisResult, i).trial_id
                == t.fingerprint
                for i in a.adjusted_ids
            )
            for a in analyses(completed_case)
        )


def test_effect_preserved_under_all_corrections(completed_case: MTCase) -> None:
    with completed_case.repo.read_snapshot(), completed_case.repo.validation_cache():
        t = trial(completed_case, "phase-5")
        _, effect = raw_results_for(completed_case.repo, t.fingerprint, t.completed_ns)
        before = effect.fingerprint, effect.estimate
        rows = tuple(
            completed_case.repo.resolve(AdjustedHypothesisResult, i)
            for a in analyses(completed_case)
            for i in a.adjusted_ids
        )
        for r in rows:
            if r.trial_id == t.fingerprint:
                assert r.effect_id == effect.fingerprint
                assert (
                    completed_case.repo.resolve(EffectSizeResult, r.effect_id).estimate
                    == before[1]
                )
        assert (effect.fingerprint, effect.estimate) == before
        assert effect.standard_error is None and effect.confidence_interval is None


@pytest.mark.parametrize(
    "mode", ["assumptions", "support", "zero", "paired", "unsupported-correlation"]
)
def test_raw_status_boundaries(mt_case: MTCase, mode: str) -> None:
    p0 = mt_case.fixture.plan("phase-5")
    metric = ResearchMetric.FORECAST_ERROR
    null = 0.0
    right: tuple[str, ...] = ()
    method = RawTestMethod.EXACT_SIGN
    if mode in ("zero", "paired"):
        metric = ResearchMetric.TARGET_RETURN
        if mode == "paired":
            method = RawTestMethod.EXACT_PAIRED_SIGN
            right = mt_case.fixture.plan("phase-6").source_ids
        else:
            sample = mt_case.repo.resolve(ResearchSample, p0.sample_ids[0])
            assert sample.target_id is not None
            truth = mt_case.repo.resolve(TargetVintage, sample.target_id)
            assert truth.value is not None
            null = truth.value
    if mode == "unsupported-correlation":
        method = RawTestMethod.CORRELATION
    p = declare_plan(
        mt_case.repo,
        "raw-" + mode,
        "raw-" + mode,
        5,
        p0.source_artifact_id,
        p0.source_ids,
        metric=metric,
        null=null,
        right=right,
        method=method,
    )
    h = mt_case.repo.resolve(HypothesisDefinition, p.hypothesis_id)
    if mode in ("assumptions", "support"):
        h = replace(
            h,
            minimum_support=2000 if mode == "support" else h.minimum_support,
            assumptions=replace(h.assumptions, independent_nonzero_signs=mode != "assumptions"),
        )
        mt_case.engine.hypothesis(h)
        p = mt_case.engine.plan(
            replace(p, attempt_key=p.attempt_key + "-replacement", hypothesis_id=h.fingerprint)
        )
    f = mt_case.engine.family(
        HypothesisFamily(
            "raw-" + mode,
            (p.fingerprint,),
            CorrectionMethod.HOLM,
            0.05,
            DependenceAssumption.UNKNOWN,
            40,
            True,
        )
    )
    t = mt_case.engine.complete(p.fingerprint, f.fingerprint, 100, 100)
    raw, effect = raw_results_for(mt_case.repo, t.fingerprint, 100)
    assert effect.estimate is not None
    if mode == "paired":
        assert raw.zero_count == raw.sample_count and raw.state is EvidenceState.INSUFFICIENT
    elif mode == "zero":
        assert raw.zero_count >= 1
    else:
        assert raw.raw_p_value is None


@pytest.mark.parametrize(
    "adaptivity", [AdaptiveTrialStatus.ADAPTIVE, AdaptiveTrialStatus.UNKNOWN]
)
def test_adaptive_or_unknown_no_final_claim(
    mt_case: MTCase, adaptivity: AdaptiveTrialStatus
) -> None:
    p, f = one_family(mt_case, "phase-5")
    parent = mt_case.engine.complete(p.fingerprint, f.fingerprint, 100, 100)
    p2 = declare_plan(
        mt_case.repo,
        "after-result",
        "later",
        5,
        p.source_artifact_id,
        p.source_ids,
        declared=110,
        adaptivity=adaptivity,
        known=(parent.fingerprint,) if adaptivity is AdaptiveTrialStatus.ADAPTIVE else (),
    )
    f2 = mt_case.engine.family(
        HypothesisFamily(
            "later",
            (p2.fingerprint,),
            CorrectionMethod.HOLM,
            0.05,
            DependenceAssumption.UNKNOWN,
            110,
            False,
        )
    )
    t2 = mt_case.engine.complete(p2.fingerprint, f2.fingerprint, 110, 110)
    result = mt_case.engine.analyze(
        f2.fingerprint, (t2.fingerprint,), FamilyCompleteness.COMPLETE, 110, 110
    )[0]
    assert result.state is EvidenceState.INTERIM
    with pytest.raises(ContractError):
        raw_results_for(mt_case.repo, t2.fingerprint, 109)
