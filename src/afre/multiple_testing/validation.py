"""Replay every completed result from pinned references, without executable payloads."""

from typing import TYPE_CHECKING

from afre.multiple_testing.adjustment import adjustment_for
from afre.multiple_testing.diagnostics import (
    DeflatedPerformanceDiagnostic,
    ResearchOverfittingDiagnostic,
)
from afre.multiple_testing.effects import EffectSizeResult
from afre.multiple_testing.evaluations import AdjustedHypothesisResult, FamilyAnalysis
from afre.multiple_testing.families import FamilyAnalysisSpec, HypothesisFamily
from afre.multiple_testing.hypotheses import HypothesisDefinition
from afre.multiple_testing.lineage import MultipleTestingAudit, audit_for
from afre.multiple_testing.observations import trial_for
from afre.multiple_testing.pvalues import PValueResult
from afre.multiple_testing.raw_tests import raw_results_for
from afre.multiple_testing.registry import TrialRegistrySnapshot
from afre.multiple_testing.registry_operations import (
    overfitting_for,
    snapshot_for,
    validate_snapshot,
)
from afre.multiple_testing.reuse_operations import reuse_for
from afre.multiple_testing.selection_bias import SelectionBiasDiagnostic, SelectionEvent
from afre.multiple_testing.selection_operations import (
    selection_diagnostic_for,
    selection_values,
)
from afre.multiple_testing.sources import validate_plan
from afre.multiple_testing.test_reuse import TestReuseDiagnostic
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.research_datasets.splits import FoldDefinition
from afre.schema import Artifact, require
from afre.target_engine.definitions import TargetDefinition

if TYPE_CHECKING:
    from afre.multiple_testing.repository import MultipleTestingRepository


def analysis_evidence(
    repo: "MultipleTestingRepository", spec: FamilyAnalysisSpec
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    raws, effects = [], []
    for identity in spec.trial_ids:
        trial = repo.resolve(ResearchTrial, identity)
        raw, effect = raw_results_for(repo, identity, trial.completed_ns)
        require(
            repo.resolve(PValueResult, raw.fingerprint) == raw
            and repo.resolve(EffectSizeResult, effect.fingerprint) == effect,
            "exact original trial raw/effect evidence",
        )
        raws.append(raw.fingerprint)
        effects.append(effect.fingerprint)
    return tuple(raws), tuple(effects)


def replay_adjustment(
    repo: "MultipleTestingRepository", spec: FamilyAnalysisSpec
) -> tuple[tuple[AdjustedHypothesisResult, ...], FamilyAnalysis]:
    if spec.fingerprint not in repo._adjustment_replays:
        repo._adjustment_replays[spec.fingerprint] = adjustment_for(
            repo, spec, *analysis_evidence(repo, spec)
        )
    return repo._adjustment_replays[spec.fingerprint]


def validate_testing(repo: "MultipleTestingRepository", value: Artifact) -> None:
    expected: Artifact = value
    if isinstance(value, HypothesisDefinition):
        require(
            repo.resolve(TargetDefinition, value.target_id).horizon.fingerprint
            == value.horizon_id,
            "hypothesis exact horizon",
        )
        require(
            repo.get_any(value.assumptions.fingerprint) == value.assumptions,
            "persisted exact test assumptions",
        )
    elif isinstance(value, TrialSpecification):
        with repo.feature_only():
            validate_plan(repo, value)
    elif isinstance(value, HypothesisFamily):
        with repo.feature_only():
            plans = tuple(repo.resolve(TrialSpecification, i) for i in value.plan_ids)
            hypotheses = tuple(
                repo.resolve(HypothesisDefinition, p.hypothesis_id) for p in plans
            )
            require(
                len(set(p.hypothesis_id for p in plans))
                <= repo.multiple_testing_bounds.hypotheses
                and len({h.metric for h in hypotheses}) <= repo.multiple_testing_bounds.metrics,
                "family hypothesis/metric bounds",
            )
            require(
                all(
                    h.family_key == value.family_key
                    and h.declared_ns <= p.declared_ns <= value.declared_ns
                    for p, h in zip(plans, hypotheses, strict=True)
                ),
                "exact declared family/hypothesis chronology",
            )
            require(
                not value.caller_attested_predeclaration
                or all(
                    value.declared_ns
                    <= repo.resolve(FoldDefinition, p.fold_id).training_cutoff_ns
                    for p in plans
                ),
                "correction membership/level fixed before held-out boundary",
            )
    elif isinstance(value, ResearchTrial):
        expected = trial_for(
            repo,
            value.plan_id,
            value.family_id,
            value.state,
            value.reason,
            value.native_result_ids,
            value.test_seal_ids,
            value.evaluation_cutoff_ns,
            value.completed_ns,
        )
    elif isinstance(value, (PValueResult, EffectSizeResult)):
        raw, effect = raw_results_for(repo, value.trial_id, value.available_ns)
        expected = raw if isinstance(value, PValueResult) else effect
    elif isinstance(value, FamilyAnalysisSpec):
        family = repo.resolve(HypothesisFamily, value.family_id)
        require(
            value.correction in (family.correction, *family.additional_corrections),
            "analysis correction not in predeclared reports",
        )
        trials = tuple(repo.resolve(ResearchTrial, i) for i in value.trial_ids)
        require(
            len({t.plan_id for t in trials}) == len(trials)
            and all(
                t.family_id == family.fingerprint
                and t.plan_id in family.plan_ids
                and t.completed_ns <= value.cutoff_ns
                for t in trials
            ),
            "analysis exact membership/cutoff",
        )
    elif isinstance(value, AdjustedHypothesisResult):
        spec = repo.resolve(FamilyAnalysisSpec, value.analysis_spec_id)
        rows, _ = replay_adjustment(repo, spec)
        matches = tuple(r for r in rows if r.plan_id == value.plan_id)
        require(len(matches) == 1, "adjusted slot must belong to exact family")
        expected = matches[0]
    elif isinstance(value, FamilyAnalysis):
        spec = repo.resolve(FamilyAnalysisSpec, value.spec_id)
        rows, expected = replay_adjustment(repo, spec)
        require(
            all(repo.resolve(AdjustedHypothesisResult, r.fingerprint) == r for r in rows),
            "exact persisted adjusted slot set",
        )
    elif isinstance(value, TrialRegistrySnapshot):
        validate_snapshot(repo, value)
        existing = repo._connection.execute(
            "SELECT 1 FROM mt_artifacts WHERE fingerprint=?", (value.fingerprint,)
        ).fetchone()
        if existing is None and value.fingerprint not in repo._frozen_registry_publications:
            require(
                value == snapshot_for(repo, value.completion_cutoff_ns, value.available_ns),
                "new registry cannot choose a research subset",
            )
    elif isinstance(value, TestReuseDiagnostic):
        expected = reuse_for(
            repo, value.registry_id, value.trial_id, value.policy_id, value.available_ns
        )
    elif isinstance(value, SelectionEvent):
        selection_values(repo, value)
    elif isinstance(value, SelectionBiasDiagnostic):
        expected = selection_diagnostic_for(
            repo, value.event_id, value.analysis_id, value.registry_id, value.available_ns
        )
    elif isinstance(value, ResearchOverfittingDiagnostic):
        expected = overfitting_for(repo, value.registry_id, value.available_ns)
    elif isinstance(value, DeflatedPerformanceDiagnostic):
        require(
            repo.resolve(TrialRegistrySnapshot, value.registry_id).available_ns
            <= value.available_ns,
            "deflation after registry",
        )
    elif isinstance(value, MultipleTestingAudit):
        expected = audit_for(repo, value.root_id)
    require(value == expected, "multiple testing semantic replay mismatch/forged result")
