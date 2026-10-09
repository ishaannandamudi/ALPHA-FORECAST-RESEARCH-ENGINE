"""Atomic declared-opportunity accounting and evidence; no search or promotion API."""

from collections.abc import Callable

from afre.multiple_testing.adjustment import adjustment_for
from afre.multiple_testing.diagnostics import (
    DeflatedPerformanceDiagnostic,
    ResearchOverfittingDiagnostic,
)
from afre.multiple_testing.evaluations import FamilyAnalysis
from afre.multiple_testing.families import FamilyAnalysisSpec, HypothesisFamily
from afre.multiple_testing.hypotheses import HypothesisDefinition
from afre.multiple_testing.lineage import MultipleTestingAudit, audit_for
from afre.multiple_testing.observations import trial_for
from afre.multiple_testing.raw_tests import raw_results_for
from afre.multiple_testing.registry import TrialRegistrySnapshot
from afre.multiple_testing.registry_operations import overfitting_for, snapshot_for
from afre.multiple_testing.repository import MultipleTestingRepository
from afre.multiple_testing.reuse_operations import reuse_for
from afre.multiple_testing.schema import (
    AdaptiveTrialStatus,
    EvidenceState,
    FamilyCompleteness,
    TrialState,
)
from afre.multiple_testing.selection_bias import SelectionBiasDiagnostic, SelectionEvent
from afre.multiple_testing.selection_operations import selection_diagnostic_for
from afre.multiple_testing.sources import source_grid
from afre.multiple_testing.test_reuse import TestReuseDiagnostic, TestReusePolicy
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.multiple_testing.validation import analysis_evidence
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require
from afre.statistical_models.evaluation import test_record


class MultipleTestingEngine:
    def __init__(self, repository: MultipleTestingRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def hypothesis(self, value: HypothesisDefinition) -> HypothesisDefinition:
        with self.repository.feature_only():
            self._publish((value.assumptions, value))
        return value

    def plan(self, value: TrialSpecification) -> TrialSpecification:
        with self.repository.feature_only():
            self._publish((value,))
        return value

    def family(self, value: HypothesisFamily) -> HypothesisFamily:
        with self.repository.feature_only():
            self._publish((value,))
        return value

    def reuse_policy(self, value: TestReusePolicy) -> TestReusePolicy:
        self._publish((value,))
        return value

    def complete(
        self,
        plan_id: str,
        family_id: str,
        cutoff_ns: int,
        completed_ns: int,
        *,
        state: TrialState = TrialState.COMPLETED,
        reason: str = "exact-native-heldout-evaluation",
        native_result_ids: tuple[str, ...] = (),
        test_seal_ids: tuple[str, ...] = (),
        test_identity: str | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> ResearchTrial:
        repo = self.repository
        seal = None
        with repo.read_snapshot(), repo.validation_cache():
            plan = repo.resolve(TrialSpecification, plan_id)
            family = repo.resolve(HypothesisFamily, family_id)
            samples = {
                s.sample_id for s in (*source_grid(repo, plan), *source_grid(repo, plan, True))
            }
            tests = any(
                m.partition is Partition.TEST and m.sample_id in samples
                for m in repo.fold_memberships(plan.fold_id)
            )
            if tests and state is TrialState.COMPLETED and not test_seal_ids:
                require(
                    test_identity is not None
                    and family.caller_attested_predeclaration
                    and plan.adaptivity is AdaptiveTrialStatus.PREDECLARED,
                    (
                        "new TEST assessment only for frozen predeclared trial; "
                        "retrospective audits require existing seals"
                    ),
                )
                seal = test_record(
                    repo,
                    plan.fold_id,
                    test_identity or "",
                    "multiple-testing-frozen-declared-trial",
                    cutoff_ns,
                )
            if snapshot_hook:
                snapshot_hook()
            value = trial_for(
                repo,
                plan_id,
                family_id,
                state,
                reason,
                native_result_ids,
                (seal.fingerprint,) if seal is not None else test_seal_ids,
                cutoff_ns,
                completed_ns,
                seal,
            )
        with repo.transaction(), repo.validation_cache():
            if seal is not None:
                repo.put(seal)
            repo.put(value)
            raw, effect = raw_results_for(repo, value.fingerprint, completed_ns)
            repo.put(raw)
            repo.put(effect)
        return value

    def analyze(
        self,
        family_id: str,
        trial_ids: tuple[str, ...],
        completeness: FamilyCompleteness,
        cutoff_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> tuple[FamilyAnalysis, ...]:
        values: list[Artifact] = []
        results = []
        with self.repository.read_snapshot(), self.repository.validation_cache():
            family = self.repository.resolve(HypothesisFamily, family_id)
            if snapshot_hook:
                snapshot_hook()
            for method in sorted(
                (family.correction, *family.additional_corrections), key=lambda m: m.value
            ):
                spec = FamilyAnalysisSpec(
                    family_id, method, trial_ids, completeness, cutoff_ns, available_ns
                )
                rows, result = adjustment_for(
                    self.repository, spec, *analysis_evidence(self.repository, spec)
                )
                values.extend((spec, *rows, result))
                results.append(result)
        self._publish(tuple(values))
        return tuple(results)

    def registry(
        self, cutoff_ns: int, available_ns: int, snapshot_hook: Callable[[], None] | None = None
    ) -> TrialRegistrySnapshot:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            value = snapshot_for(self.repository, cutoff_ns, available_ns)
            if snapshot_hook:
                snapshot_hook()
        self.repository._frozen_registry_publications.add(value.fingerprint)
        try:
            self._publish((value,))
        finally:
            self.repository._frozen_registry_publications.discard(value.fingerprint)
        return value

    def _diagnostic(self, compute: Callable[[], Artifact]) -> Artifact:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            value = compute()
        self._publish((value,))
        return value

    def test_reuse(
        self, registry_id: str, trial_id: str, policy_id: str, available_ns: int
    ) -> TestReuseDiagnostic:
        value = self._diagnostic(
            lambda: reuse_for(self.repository, registry_id, trial_id, policy_id, available_ns)
        )
        assert isinstance(value, TestReuseDiagnostic)
        return value

    def record_selection(self, event: SelectionEvent) -> SelectionEvent:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            self.repository._validate_links(event)
        self._publish((event,))
        return event

    def selection_bias(
        self, event_id: str, analysis_id: str, registry_id: str, available_ns: int
    ) -> SelectionBiasDiagnostic:
        value = self._diagnostic(
            lambda: selection_diagnostic_for(
                self.repository, event_id, analysis_id, registry_id, available_ns
            )
        )
        assert isinstance(value, SelectionBiasDiagnostic)
        return value

    def overfitting(self, registry_id: str, available_ns: int) -> ResearchOverfittingDiagnostic:
        value = self._diagnostic(
            lambda: overfitting_for(self.repository, registry_id, available_ns)
        )
        assert isinstance(value, ResearchOverfittingDiagnostic)
        return value

    def deflated(self, registry_id: str, available_ns: int) -> DeflatedPerformanceDiagnostic:
        value = DeflatedPerformanceDiagnostic(
            registry_id,
            EvidenceState.UNSUPPORTED,
            "no-portfolio-return-series-or-justified-generic-deflation-contract",
            available_ns,
        )
        self._publish((value,))
        return value

    def audit(self, root_id: str) -> MultipleTestingAudit:
        value = self._diagnostic(lambda: audit_for(self.repository, root_id))
        assert isinstance(value, MultipleTestingAudit)
        return value
