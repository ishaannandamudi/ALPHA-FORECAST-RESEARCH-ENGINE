"""AFRE-19 declared research trials and multiple-testing controls, schema1.0."""

from afre.multiple_testing.corrections import adjust_pvalues
from afre.multiple_testing.diagnostics import (
    DeflatedPerformanceDiagnostic,
    ResearchOverfittingDiagnostic,
)
from afre.multiple_testing.effects import EffectSizeResult
from afre.multiple_testing.engine import MultipleTestingEngine
from afre.multiple_testing.evaluations import AdjustedHypothesisResult, FamilyAnalysis
from afre.multiple_testing.families import FamilyAnalysisSpec, HypothesisFamily
from afre.multiple_testing.hypotheses import HypothesisDefinition, TestAssumptions
from afre.multiple_testing.lineage import MultipleTestingAudit
from afre.multiple_testing.pvalues import PValueResult, fair_sign_pvalue
from afre.multiple_testing.registry import TrialRegistrySnapshot
from afre.multiple_testing.repository import MultipleTestingRepository
from afre.multiple_testing.schema import (
    AdaptiveTrialStatus,
    CorrectionMethod,
    DependenceAssumption,
    DescriptiveSelectionRule,
    EvidenceState,
    FamilyCompleteness,
    HypothesisDirection,
    MultipleTestingBounds,
    RawTestMethod,
    ResearchMetric,
    TestReuseStatus,
    TrialState,
)
from afre.multiple_testing.selection_bias import SelectionBiasDiagnostic, SelectionEvent
from afre.multiple_testing.test_reuse import TestReuseDiagnostic, TestReusePolicy
from afre.multiple_testing.trials import ResearchTrial, TrialObservation, TrialSpecification

__all__ = [
    "AdaptiveTrialStatus",
    "AdjustedHypothesisResult",
    "CorrectionMethod",
    "DeflatedPerformanceDiagnostic",
    "DependenceAssumption",
    "DescriptiveSelectionRule",
    "EffectSizeResult",
    "EvidenceState",
    "FamilyAnalysis",
    "FamilyAnalysisSpec",
    "FamilyCompleteness",
    "HypothesisDefinition",
    "HypothesisDirection",
    "HypothesisFamily",
    "MultipleTestingAudit",
    "MultipleTestingBounds",
    "MultipleTestingEngine",
    "MultipleTestingRepository",
    "PValueResult",
    "RawTestMethod",
    "ResearchMetric",
    "ResearchOverfittingDiagnostic",
    "ResearchTrial",
    "SelectionBiasDiagnostic",
    "SelectionEvent",
    "TestAssumptions",
    "TestReuseDiagnostic",
    "TestReusePolicy",
    "TestReuseStatus",
    "TrialObservation",
    "TrialRegistrySnapshot",
    "TrialSpecification",
    "TrialState",
    "adjust_pvalues",
    "fair_sign_pvalue",
]
