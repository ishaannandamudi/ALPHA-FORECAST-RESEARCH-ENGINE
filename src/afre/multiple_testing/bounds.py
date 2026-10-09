"""Lowerable limits apply before storage and bounded registry/lineage enumeration."""

from afre.multiple_testing.families import FamilyAnalysisSpec, HypothesisFamily
from afre.multiple_testing.lineage import MultipleTestingAudit
from afre.multiple_testing.registry import TrialRegistrySnapshot
from afre.multiple_testing.schema import MultipleTestingBounds
from afre.multiple_testing.selection_bias import SelectionEvent
from afre.multiple_testing.test_reuse import TestReuseDiagnostic
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.schema import Artifact, require
from afre.serialization import canonical_json


def check_bounds(b: MultipleTestingBounds, value: Artifact) -> None:
    if isinstance(value, HypothesisFamily):
        require(len(value.plan_ids) <= b.trials, "family trial bound")
    if isinstance(value, TrialSpecification):
        require(
            len(value.source_ids) <= b.samples
            and len(value.right_source_ids) <= b.samples
            and len(value.sample_ids) <= b.samples
            and len(value.membership_ids) <= b.samples
            and len(value.known_trial_ids) <= b.trials,
            "trial source/sample/adaptivity bounds",
        )
    if isinstance(value, ResearchTrial):
        require(
            len(value.observations) <= b.samples and len(value.test_seal_ids) <= b.test_history,
            "completed trial observation/history bounds",
        )
    if isinstance(value, FamilyAnalysisSpec):
        require(len(value.trial_ids) <= b.trials, "analysis trial bound")
    if isinstance(value, TrialRegistrySnapshot):
        require(
            len(value.trial_ids) <= b.trials
            and len(value.plan_ids) <= b.trials
            and len(value.family_ids) <= b.trials
            and len(value.selection_event_ids) <= b.selection_events
            and len(value.native_test_seal_ids) <= b.test_history,
            "registry history/opportunity bounds",
        )
    if isinstance(value, SelectionEvent):
        require(len(value.candidate_trial_ids) <= b.trials, "selection candidate bound")
    if isinstance(value, TestReuseDiagnostic):
        require(
            len(value.exact_seal_counts) <= b.test_history
            and len(value.scope_trial_ids) <= b.trials,
            "TEST reuse history bound",
        )
    if isinstance(value, MultipleTestingAudit):
        require(len(value.node_ids) <= b.audit_nodes, "audit node bound")
    require(
        len(canonical_json(value).encode()) <= b.serialized_bytes,
        "multiple testing serialized payload bound",
    )
