"""AFRE20 deterministic TRAIN/VALIDATION model selection. No ensemble fusion."""

from afre.selection.budgets import ResourceBudget, ResourceUsage
from afre.selection.definitions import (
    CandidateFamilyPlan,
    CandidateSpec,
    DiscreteDimension,
    NativeCandidateRecipe,
    SearchSpace,
    SelectionRequest,
)
from afre.selection.engine import SelectionEngine
from afre.selection.enumeration import enumerate_candidates
from afre.selection.registry import CandidateRegistrySnapshot
from afre.selection.repository import SelectionRepository
from afre.selection.results import (
    CandidateFitResult,
    CandidateValidationResult,
    SelectionResult,
)
from afre.selection.schema import (
    CandidateStatus,
    SelectionBounds,
    SelectionCriterion,
    SelectionReadRole,
    SelectionStatus,
)

__all__ = [
    "CandidateFamilyPlan",
    "CandidateSpec",
    "DiscreteDimension",
    "NativeCandidateRecipe",
    "SearchSpace",
    "SelectionRequest",
    "SelectionEngine",
    "enumerate_candidates",
    "CandidateRegistrySnapshot",
    "SelectionRepository",
    "CandidateFitResult",
    "CandidateValidationResult",
    "SelectionResult",
    "CandidateStatus",
    "SelectionBounds",
    "SelectionCriterion",
    "SelectionReadRole",
    "SelectionStatus",
    "ResourceBudget",
    "ResourceUsage",
]
