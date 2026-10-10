"""Explicit native recipes, fully bound grids and target-free planned families."""

from dataclasses import dataclass
from itertools import product
from math import prod

from afre.event_conditioned.definitions import EventConditioningSpec
from afre.ids import validate_fingerprint
from afre.nonlinear.definitions import NonlinearModelSpec
from afre.probabilistic.definitions import ProbabilisticModelSpec
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.schema import Artifact, contract, require
from afre.selection.budgets import ResourceBudget
from afre.selection.schema import IMPLEMENTATION, SelectionCriterion
from afre.sequence.definitions import SequenceModelSpec
from afre.statistical_models.definitions import BaselineModelSpec


@contract("sel_dimension")
@dataclass(frozen=True, slots=True)
class DiscreteDimension(Artifact):
    name: str
    values: tuple[str, ...]

    def _normalize(self) -> None:
        require(len(set(self.values)) == len(self.values), "duplicate dimension value")
        object.__setattr__(self, "values", tuple(sorted(self.values)))

    def _validate(self) -> None:
        require(
            1 <= len(self.values) <= 128
            and len(self.name) <= 64
            and all(len(v) <= 256 for v in self.values),
            "dimension bounds",
        )


@contract("sel_recipe")
@dataclass(frozen=True, slots=True)
class NativeCandidateRecipe(Artifact):
    native_spec: (
        BaselineModelSpec
        | ProbabilisticModelSpec
        | EventConditioningSpec
        | RegimeConditioningSpec
        | NonlinearModelSpec
        | SequenceModelSpec
    )
    choices: tuple[tuple[str, str], ...]
    train_input_ids: tuple[str, ...] = ()
    validation_bindings: tuple[tuple[str, str], ...] = ()
    train_bindings: tuple[tuple[str, str], ...] = ()
    preprocessing_ids: tuple[str, ...] = ()
    feature_ids: tuple[str, ...] = ()
    orthogonal_feature_ids: tuple[str, ...] = ()
    # Extra diagnostics are lineage metadata, never ranking inputs.
    diagnostic_ids: tuple[str, ...] = ()
    implementation: str = IMPLEMENTATION

    def _normalize(self) -> None:
        for name in ("choices", "validation_bindings", "train_bindings"):
            items = getattr(self, name)
            require(len({i[0] for i in items}) == len(items), "duplicate recipe binding")
            object.__setattr__(self, name, tuple(sorted(items)))
        for name in (
            "train_input_ids",
            "preprocessing_ids",
            "feature_ids",
            "orthogonal_feature_ids",
            "diagnostic_ids",
        ):
            items = getattr(self, name)
            require(len(set(items)) == len(items), "duplicate recipe source")
            object.__setattr__(self, name, tuple(sorted(items)))

    def _validate(self) -> None:
        require(
            len(self.choices) <= 16
            and len(self.train_input_ids) <= 2000
            and len(self.train_bindings) <= 2000
            and len(self.validation_bindings) <= 2000
            and len(self.preprocessing_ids) <= 32
            and len(self.feature_ids) <= 256
            and len(self.orthogonal_feature_ids) <= 32
            and len(self.diagnostic_ids) <= 32
            and self.implementation == IMPLEMENTATION,
            "recipe bounds/implementation",
        )
        for name, value in self.choices:
            require(len(name) <= 64 and len(value) <= 256, "recipe choice bounds")
        for identity in (
            *self.train_input_ids,
            *self.preprocessing_ids,
            *self.feature_ids,
            *self.orthogonal_feature_ids,
            *self.diagnostic_ids,
            *(i for pair in (*self.train_bindings, *self.validation_bindings) for i in pair),
        ):
            validate_fingerprint(identity)

    @property
    def native_phase(self) -> int:
        return {
            BaselineModelSpec: 5,
            ProbabilisticModelSpec: 6,
            EventConditioningSpec: 10,
            RegimeConditioningSpec: 11,
            NonlinearModelSpec: 13,
            SequenceModelSpec: 14,
        }[type(self.native_spec)]


@contract("sel_space")
@dataclass(frozen=True, slots=True)
class SearchSpace(Artifact):
    search_key: str
    target_id: str
    horizon_id: str
    dataset_id: str
    fold_id: str
    dimensions: tuple[DiscreteDimension, ...]
    recipes: tuple[NativeCandidateRecipe, ...]
    budget: ResourceBudget
    criterion: SelectionCriterion
    validation_sample_ids: tuple[str, ...]
    declared_ns: int
    minimum_support: int = 2
    permit_single_valid: bool = False
    secondary_criterion: SelectionCriterion | None = None
    baseline_recipe_id: str | None = None
    # Failure trials use this explicitly declared native VALIDATION protocol anchor.
    # No anchor observations are attributed to failed candidates.
    failure_anchor_source_ids: tuple[str, ...] = ()
    tie_rule: str = "lexicographic-metrics-then-candidate-fingerprint-v1"
    implementation: str = IMPLEMENTATION

    def _normalize(self) -> None:
        object.__setattr__(
            self, "validation_sample_ids", tuple(sorted(self.validation_sample_ids))
        )
        self.ordered("dimensions", "name")
        self.ordered("recipes", "fingerprint")
        require(
            len(set(self.failure_anchor_source_ids)) == len(self.failure_anchor_source_ids),
            "duplicate failure anchor",
        )
        object.__setattr__(
            self, "failure_anchor_source_ids", tuple(sorted(self.failure_anchor_source_ids))
        )

    def _validate(self) -> None:
        for identity in (
            self.target_id,
            self.horizon_id,
            self.dataset_id,
            self.fold_id,
            self.baseline_recipe_id,
            *self.failure_anchor_source_ids,
        ):
            if identity:
                validate_fingerprint(identity)
        count = prod(len(d.values) for d in self.dimensions)
        require(
            1 <= len(self.dimensions) <= 16
            and 1 <= count <= self.budget.max_candidates
            and len(self.recipes) == count <= 128,
            "candidate product bound",
        )
        expected = {
            tuple(zip((d.name for d in self.dimensions), values, strict=True))
            for values in product(*(d.values for d in self.dimensions))
        }
        require(
            {r.choices for r in self.recipes} == expected, "exact fully bound Cartesian grid"
        )
        require(
            1
            <= len(self.validation_sample_ids)
            == len(set(self.validation_sample_ids))
            <= 2000,
            "declared validation sample bound",
        )
        for i in self.validation_sample_ids:
            validate_fingerprint(i, "r_sample")
        require(
            1 <= self.minimum_support <= 2000
            and len(self.search_key) <= 128
            and len(self.failure_anchor_source_ids) <= 2000
            and self.criterion is not self.secondary_criterion
            and self.tie_rule == "lexicographic-metrics-then-candidate-fingerprint-v1"
            and self.implementation == IMPLEMENTATION,
            "selection protocol",
        )
        require(
            self.baseline_recipe_id is None
            or self.baseline_recipe_id in {r.fingerprint for r in self.recipes},
            "explicit baseline in complete roster",
        )


@contract("sel_candidate")
@dataclass(frozen=True, slots=True)
class CandidateSpec(Artifact):
    search_space_id: str
    recipe: NativeCandidateRecipe
    target_id: str
    horizon_id: str
    dataset_id: str
    fold_id: str
    implementation: str = IMPLEMENTATION

    def _validate(self) -> None:
        for identity in (
            self.search_space_id,
            self.target_id,
            self.horizon_id,
            self.dataset_id,
            self.fold_id,
        ):
            validate_fingerprint(identity)
        require(self.implementation == IMPLEMENTATION, "candidate implementation")


@contract("sel_request")
@dataclass(frozen=True, slots=True)
class SelectionRequest(Artifact):
    search_space_id: str
    truth_cutoff_ns: int
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.search_space_id, "sel_space")
        require(self.truth_cutoff_ns <= self.available_ns, "request clocks")


@contract("sel_family_plan")
@dataclass(frozen=True, slots=True)
class CandidateFamilyPlan(Artifact):
    request_id: str
    search_space_id: str
    candidate_ids: tuple[str, ...]
    declared_ns: int

    def _normalize(self) -> None:
        require(
            len(set(self.candidate_ids)) == len(self.candidate_ids),
            "duplicate planned candidate",
        )
        object.__setattr__(self, "candidate_ids", tuple(sorted(self.candidate_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.request_id, "sel_request")
        validate_fingerprint(self.search_space_id)
        require(1 <= len(self.candidate_ids) <= 128, "planned opportunity bound")
        for i in self.candidate_ids:
            validate_fingerprint(i, "sel_candidate")
