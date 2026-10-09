"""Thirty-six checked offline steps with immutable native opportunities and replay."""

import hashlib
import json
import statistics
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.costs import CostInputRole, CostResearchEngine
from afre.multiple_testing import (
    AdaptiveTrialStatus,
    AdjustedHypothesisResult,
    CorrectionMethod,
    DependenceAssumption,
    DescriptiveSelectionRule,
    EffectSizeResult,
    EvidenceState,
    FamilyAnalysisSpec,
    FamilyCompleteness,
    HypothesisDefinition,
    HypothesisFamily,
    MultipleTestingEngine,
    MultipleTestingRepository,
    ResearchMetric,
    SelectionEvent,
    TestReusePolicy,
    TestReuseStatus,
    TrialState,
)
from afre.multiple_testing.raw_tests import raw_results_for
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from afre.target_engine.definitions import TargetDefinition
from afre.target_engine.market_data import TargetBar
from afre.target_engine.models import TargetVintage
from examples.costs_workflow import assess, corrected_input
from examples.multiple_testing_fixture import build_fixture, declare_plan
from examples.multiple_testing_oracles import correction_oracle
from examples.multiple_testing_workflow import complete_fixture

STEPS = (
    "native candidate models",
    "explicit family",
    "multiple horizons",
    "multiple environments",
    "multiple cost scenarios",
    "null/alternative/direction",
    "supported exact raw p-values",
    "separate effects",
    "Bonferroni",
    "Holm",
    "BH",
    "independent adjusted verification",
    "unsupported raw test",
    "failed attempt",
    "open family",
    "complete family",
    "TEST accounting",
    "first/reused TEST",
    "predeclared",
    "adaptive",
    "selection event",
    "winner/median spreads",
    "effect preservation",
    "nonsignificant retained",
    "no promotion",
    "no pruning",
    "TEST truth isolation",
    "actual1h/1d",
    "AFRE17 environments",
    "AFRE18 costs",
    "corrected source new trial",
    "old adjusted unchanged",
    "registry",
    "restart",
    "deterministic semantic digest",
    "bounded unified audit",
)


def payload_digest(repo: MultipleTestingRepository) -> str:
    with repo.read_snapshot(), repo.validation_cache():
        payloads = tuple(
            canonical_json(repo.get_any(i))
            for (i,) in repo._connection.execute(
                "SELECT fingerprint FROM mt_artifacts ORDER BY fingerprint"
            )
        )
    return hashlib.sha256("\n".join(payloads).encode()).hexdigest()


def run(path: Path, reverse: bool = False) -> dict[str, object]:
    checks: dict[str, bool] = {}
    with MultipleTestingRepository(path) as repo:
        f = build_fixture(repo, reverse)
        e = MultipleTestingEngine(repo)
        policy = e.reuse_policy(TestReusePolicy(3, 40))
        baseline_models = repo._connection.execute(
            "SELECT count(*) FROM m_artifacts"
        ).fetchone()[0]
        checks[STEPS[0]] = {p.native_phase for p in f.plans} == set(range(5, 19))
        checks[STEPS[1]] = set(f.family.plan_ids) == {p.fingerprint for p in f.plans}
        checks[STEPS[2]] = len(f.cutoffs) == 2
        checks[STEPS[3]] = len({p.environment_id for p in f.plans if p.environment_id}) == 2
        checks[STEPS[4]] = len({p.cost_scenario_id for p in f.plans if p.cost_scenario_id}) == 2
        p = f.plan("phase-5")
        h = repo.get_any(p.hypothesis_id)
        checks[STEPS[5]] = bool(getattr(h, "null", None) and getattr(h, "alternative", None))
        # Freeze each use snapshot; later writes cannot change historical membership.
        diagnostics = []
        for j in range(3):
            ptest = f.plan(f"test-{j}")
            t = e.complete(
                ptest.fingerprint,
                f.family.fingerprint,
                100,
                100,
                test_identity="frozen-mt-test",
            )
            reg = e.registry(100, 100)
            diagnostics.append(
                e.test_reuse(reg.fingerprint, t.fingerprint, policy.fingerprint, 100)
            )
        trials, analyses = complete_fixture(e, f, reverse)
        at = max(t.completed_ns for t in trials)
        with repo.read_snapshot(), repo.validation_cache():
            rows = tuple(
                repo.resolve(AdjustedHypothesisResult, i)
                for a in analyses
                for i in a.adjusted_ids
            )
            raws = tuple(
                raw_results_for(repo, t.fingerprint, t.completed_ns)[0] for t in trials
            )
            effects = tuple(
                raw_results_for(repo, t.fingerprint, t.completed_ns)[1] for t in trials
            )
        checks[STEPS[6]] = any(r.state is EvidenceState.AVAILABLE for r in raws)
        checks[STEPS[7]] = all(e.confidence_interval is None for e in effects)
        methods = {repo.resolve(FamilyAnalysisSpec, a.spec_id).correction for a in analyses}
        for index, method in (
            (8, CorrectionMethod.BONFERRONI),
            (9, CorrectionMethod.HOLM),
            (10, CorrectionMethod.BENJAMINI_HOCHBERG),
        ):
            checks[STEPS[index]] = method in methods
        numerical_errors: list[float] = []
        for method in methods:
            group = tuple(r for r in rows if r.correction is method)
            expected = correction_oracle(
                tuple((r.plan_id, r.raw_p_value) for r in group), method
            )
            numerical_errors.extend(
                abs(r.adjusted_value - expected[r.plan_id])
                for r in group
                if r.adjusted_value is not None
            )
        checks[STEPS[11]] = max(numerical_errors, default=0.0) <= 2e-16
        checks[STEPS[12]] = any(r.state is EvidenceState.UNSUPPORTED for r in raws)
        checks[STEPS[13]] = sum(t.state is not TrialState.COMPLETED for t in trials) == 2
        interim = e.analyze(
            f.family.fingerprint, (trials[0].fingerprint,), FamilyCompleteness.OPEN, at, at
        )
        checks[STEPS[14]] = all(a.state is not EvidenceState.AVAILABLE for a in interim)
        checks[STEPS[15]] = all(a.completeness is FamilyCompleteness.COMPLETE for a in analyses)
        checks[STEPS[16]] = [d.use_count for d in diagnostics] == [1, 2, 3]
        checks[STEPS[17]] = [d.tracked_status for d in diagnostics] == [
            TestReuseStatus.FIRST_USE,
            TestReuseStatus.REUSED,
            TestReuseStatus.HEAVILY_REUSED,
        ]
        checks[STEPS[18]] = all(
            p.adaptivity is AdaptiveTrialStatus.PREDECLARED for p in f.plans
        )
        parent = next(t for t in trials if t.plan_id == f.plan("phase-5").fingerprint)
        adaptive = declare_plan(
            repo,
            "caller-adaptive",
            "adaptive-family",
            5,
            f.plan("phase-5").source_artifact_id,
            f.plan("phase-5").source_ids,
            declared=110,
            adaptivity=AdaptiveTrialStatus.ADAPTIVE,
            known=(parent.fingerprint,),
        )
        af = e.family(
            HypothesisFamily(
                "adaptive-family",
                (adaptive.fingerprint,),
                CorrectionMethod.HOLM,
                0.05,
                DependenceAssumption.UNKNOWN,
                110,
                False,
            )
        )
        adaptive_trial = e.complete(adaptive.fingerprint, af.fingerprint, 110, 110)
        adaptive_analysis = e.analyze(
            af.fingerprint, (adaptive_trial.fingerprint,), FamilyCompleteness.COMPLETE, 110, 110
        )[0]
        checks[STEPS[19]] = adaptive_analysis.state is EvidenceState.INTERIM
        candidates = tuple(
            t
            for t in trials
            if t.plan_id
            in {f.plan(k).fingerprint for k in ("phase-5", "phase-6", "phase-13", "phase-14")}
        )
        values = {
            t.fingerprint: raw_results_for(repo, t.fingerprint, at)[1].estimate
            for t in candidates
        }
        assert all(v is not None for v in values.values())
        ordered = tuple(sorted(values, key=lambda i: (-(values[i] or 0.0), i)))
        event = e.record_selection(
            SelectionEvent(
                tuple(values),
                (ordered[0],),
                DescriptiveSelectionRule.MAX_METRIC,
                True,
                1,
                None,
                at,
                at,
                ordering=ordered,
            )
        )
        registry = e.registry(at, at)
        holm = next(
            a
            for a in analyses
            if repo.resolve(FamilyAnalysisSpec, a.spec_id).correction is CorrectionMethod.HOLM
        )
        diagnostic = e.selection_bias(
            event.fingerprint, holm.fingerprint, registry.fingerprint, at
        )
        checks[STEPS[20]] = event.candidate_trial_ids == tuple(sorted(values))
        median = float(statistics.median(v for v in values.values() if v is not None))
        checks[STEPS[21]] = diagnostic.winner_minus_median == (
            values[ordered[0]] or 0.0
        ) - median and diagnostic.winner_minus_next == (values[ordered[0]] or 0.0) - (
            values[ordered[1]] or 0.0
        )
        checks[STEPS[22]] = all(
            repo.resolve(EffectSizeResult, r.effect_id).estimate
            == next(e.estimate for e in effects if e.fingerprint == r.effect_id)
            for r in rows
            if r.effect_id
        )
        checks[STEPS[23]] = any(r.reject is False for r in rows) and len(
            registry.trial_ids
        ) >= len(trials)
        checks[STEPS[24]] = (
            repo._connection.execute("SELECT count(*) FROM m_artifacts").fetchone()[0]
            == baseline_models
        )
        checks[STEPS[25]] = {t.fingerprint for t in trials} <= set(registry.trial_ids)
        old_family, old_adjusted = canonical_json(f.family), canonical_json(holm)
        sample = repo.resolve(ResearchSample, min(f.plan("test-0").sample_ids))
        assert sample.target_id is not None
        truth = repo.resolve(TargetVintage, sample.target_id)
        assert truth.endpoint_bar_id is not None
        bar = repo.resolve(TargetBar, truth.endpoint_bar_id)
        with repo.transaction():
            repo.put(replace(bar, close=(bar.close or 0) + 999, predecessor_id=bar.fingerprint))
        checks[STEPS[26]] = canonical_json(repo.get_any(f.family.fingerprint)) == old_family
        durations = {
            repo.resolve(
                TargetDefinition, repo.resolve(HypothesisDefinition, p.hypothesis_id).target_id
            ).horizon.duration_ns
            for p in f.plans
            if p.attempt_key.startswith("actual-")
        }
        checks[STEPS[27]] = durations == {3_600_000_000_000, 86_400_000_000_000}
        checks[STEPS[28]] = len({p.fingerprint for p in f.plans if p.native_phase == 17}) == 2
        checks[STEPS[29]] = len(f.cost_results) == 2
        old = min(
            (i for i in f.native.inputs if i.role is CostInputRole.MODEL_VALUE),
            key=lambda i: i.fingerprint,
        )
        correction = replace(old, value=(old.value or 0) + 1, revision="correction2")
        ce = CostResearchEngine(repo)
        ce.publish_input(correction)
        scenario = corrected_input(f.native.scenario, old.fingerprint, correction)
        result = assess(ce, scenario)[2]
        corrected_plan = declare_plan(
            repo,
            "corrected-cost",
            "corrected-family",
            18,
            scenario.fingerprint,
            scenario.source_ids,
            metric=ResearchMetric.NET_CONTRIBUTION,
            cost=scenario.fingerprint,
        )
        cf = e.family(
            HypothesisFamily(
                "corrected-family",
                (corrected_plan.fingerprint,),
                CorrectionMethod.HOLM,
                0.05,
                DependenceAssumption.UNKNOWN,
                40,
                True,
            )
        )
        corrected_trial = e.complete(
            corrected_plan.fingerprint,
            cf.fingerprint,
            100,
            100,
            native_result_ids=(result.fingerprint,),
        )
        checks[STEPS[30]] = corrected_trial.plan_id != f.plan("cost-0").fingerprint
        checks[STEPS[31]] = canonical_json(repo.get_any(holm.fingerprint)) == old_adjusted
        registry = e.registry(at, at)
        overfitting = e.overfitting(registry.fingerprint, at)
        deflated = e.deflated(registry.fingerprint, at)
        checks[STEPS[32]] = (
            overfitting.planned_count == len(registry.plan_ids)
            and deflated.state is EvidenceState.UNSUPPORTED
        )
        audit = e.audit(holm.fingerprint)
        checks[STEPS[35]] = 0 < len(audit.node_ids) <= repo.multiple_testing_bounds.audit_nodes
        before = payload_digest(repo)
    with MultipleTestingRepository(path) as restarted:
        checks[STEPS[33]] = canonical_json(restarted.get_any(holm.fingerprint)) == old_adjusted
        digest = payload_digest(restarted)
        checks[STEPS[34]] = digest == before
    assert len(checks) == 36 and all(checks.values()), checks
    return {
        "steps": tuple((s, checks[s]) for s in STEPS),
        "digest": digest,
        "trials": len(trials),
        "family_size": len(f.plans),
        "audit_nodes": len(audit.node_ids),
        "max_numerical_error": max(numerical_errors, default=0.0),
    }


def main() -> None:
    with TemporaryDirectory() as folder:
        print(json.dumps(run(Path(folder) / "multiple-testing.sqlite"), indent=2))


if __name__ == "__main__":
    main()
