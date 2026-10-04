"""Immutable temporal split plans, typed embargo grids and explicit exclusions."""

from dataclasses import dataclass

from afre.feature_store.models import exclude_target_reference
from afre.ids import validate_fingerprint
from afre.research_datasets.schema import (
    SPLITTER_VERSION,
    EmbargoBasis,
    EmbargoDirection,
    Partition,
    PurgeRule,
    PurgeScope,
    SplitStrategy,
)
from afre.schema import Artifact, contract, require
from afre.time import TimeRange


@contract("r_bar_grid")
@dataclass(frozen=True, slots=True)
class EmbargoBarGrid(Artifact):
    calendar_id: str
    bar_definition: str
    version: str
    source_id: str
    known_ns: int
    periods: tuple[TimeRange, ...]

    def _normalize(self) -> None:
        self.ordered("periods", "start_ns")

    def _validate(self) -> None:
        exclude_target_reference(self.source_id)
        validate_fingerprint(self.source_id)
        require(bool(self.periods), "empty embargo bar grid")
        require(
            all(
                a.end_ns <= b.start_ns
                for a, b in zip(self.periods, self.periods[1:], strict=False)
            ),
            "overlapping embargo bars",
        )


@contract("r_purge_policy")
@dataclass(frozen=True, slots=True)
class PurgePolicy(Artifact):
    rule: PurgeRule = PurgeRule.TARGET_INTERVAL_OVERLAP
    scope: PurgeScope = PurgeScope.SECURITY


@contract("r_embargo_policy")
@dataclass(frozen=True, slots=True)
class EmbargoPolicy(Artifact):
    basis: EmbargoBasis = EmbargoBasis.ELAPSED_TIME
    count: int = 0
    direction: EmbargoDirection = EmbargoDirection.AFTER
    calendar_id: str | None = None
    bar_grid: EmbargoBarGrid | None = None

    def _validate(self) -> None:
        require(self.count >= 0, "negative embargo length")
        require(
            (self.calendar_id is not None) == (self.basis is EmbargoBasis.TRADING_SESSIONS),
            "session embargo requires exact calendar identity",
        )
        if self.calendar_id is not None:
            validate_fingerprint(self.calendar_id, "u_calendar")
        require(
            (self.bar_grid is not None) == (self.basis is EmbargoBasis.BARS),
            "bar embargo requires declared stream grid",
        )


@contract("r_split_definition")
@dataclass(frozen=True, slots=True)
class SplitDefinition(Artifact):
    name: str
    version: str
    strategy: SplitStrategy
    train: TimeRange
    validation: TimeRange
    training_cutoff_ns: int
    step_ns: int = 0
    fold_count: int = 1
    test: TimeRange | None = None
    purge: PurgePolicy = PurgePolicy()
    embargo: EmbargoPolicy = EmbargoPolicy()
    preprocessing_spec_ids: tuple[str, ...] = ()
    parent_fold_id: str | None = None
    implementation_version: str = SPLITTER_VERSION

    def _normalize(self) -> None:
        require(
            len(set(self.preprocessing_spec_ids)) == len(self.preprocessing_spec_ids),
            "duplicate preprocessing specs",
        )
        object.__setattr__(
            self, "preprocessing_spec_ids", tuple(sorted(self.preprocessing_spec_ids))
        )

    def _validate(self) -> None:
        require(self.name.startswith("split."), "split namespace required")
        require(self.fold_count > 0 and self.step_ns >= 0, "invalid fold count/step")
        require(
            self.train.end_ns <= self.training_cutoff_ns <= self.validation.start_ns,
            "training cutoff crosses validation boundary",
        )
        require(self.train.end_ns <= self.validation.start_ns, "train/validation overlap")
        if self.strategy is SplitStrategy.FIXED_HOLDOUT:
            require(self.fold_count == 1 and self.step_ns == 0, "fixed holdout has one fold")
        else:
            require(
                self.fold_count == 1 or self.step_ns > 0, "repeated folds require positive step"
            )
        if self.test is not None:
            require(
                self.test.start_ns
                >= self.validation.end_ns + self.step_ns * (self.fold_count - 1),
                "sealed test overlaps validation/training schedule",
            )
        for identity in self.preprocessing_spec_ids:
            validate_fingerprint(identity, "r_preprocessing_spec")
        if self.parent_fold_id is not None:
            validate_fingerprint(self.parent_fold_id, "r_fold")


@contract("r_fold")
@dataclass(frozen=True, slots=True)
class FoldDefinition(Artifact):
    dataset_id: str
    split_definition_id: str
    ordinal: int
    train: TimeRange
    validation: TimeRange
    test: TimeRange | None
    training_cutoff_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.dataset_id, "r_dataset")
        validate_fingerprint(self.split_definition_id, "r_split_definition")
        require(self.ordinal >= 0, "negative fold ordinal")
        require(
            self.train.end_ns <= self.training_cutoff_ns <= self.validation.start_ns,
            "fold cutoff crosses validation",
        )
        require(
            self.test is None or self.validation.end_ns <= self.test.start_ns,
            "fold validation/test overlap",
        )


@contract("r_membership")
@dataclass(frozen=True, slots=True)
class FoldMembership(Artifact):
    fold_id: str
    sample_id: str
    partition: Partition
    reason: str

    def _validate(self) -> None:
        validate_fingerprint(self.fold_id, "r_fold")
        validate_fingerprint(self.sample_id, "r_sample")


@contract("r_split")
@dataclass(frozen=True, slots=True)
class ResearchSplit(Artifact):
    dataset_id: str
    definition_id: str
    fold_ids: tuple[str, ...]

    def _validate(self) -> None:
        validate_fingerprint(self.dataset_id, "r_dataset")
        validate_fingerprint(self.definition_id, "r_split_definition")
        require(
            bool(self.fold_ids) and len(set(self.fold_ids)) == len(self.fold_ids),
            "invalid split folds",
        )
        for identity in self.fold_ids:
            validate_fingerprint(identity, "r_fold")


@contract("r_test_evaluation")
@dataclass(frozen=True, slots=True)
class TestEvaluation(Artifact):
    fold_id: str
    evaluation_id: str
    purpose: str
    evaluated_ns: int
    sample_ids: tuple[str, ...]
    previous_evaluation_ids: tuple[str, ...] = ()

    def _normalize(self) -> None:
        for name in ("sample_ids", "previous_evaluation_ids"):
            values = getattr(self, name)
            require(len(set(values)) == len(values), "duplicate test evaluation evidence")
            object.__setattr__(self, name, tuple(sorted(values)))

    def _validate(self) -> None:
        validate_fingerprint(self.fold_id, "r_fold")
        for identity in self.sample_ids:
            validate_fingerprint(identity, "r_sample")
        for identity in self.previous_evaluation_ids:
            validate_fingerprint(identity, "r_test_evaluation")
