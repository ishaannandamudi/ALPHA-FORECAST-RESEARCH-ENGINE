"""Immutable fit, exact validation witness and complete selection decision."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.selection.budgets import ResourceUsage
from afre.selection.schema import CandidateStatus, SelectionCriterion, SelectionStatus


@contract("sel_fit")
@dataclass(frozen=True, slots=True)
class CandidateFitResult(Artifact):
    candidate_id: str
    model_id: str | None
    preprocessing_ids: tuple[str, ...]
    forecast_ids: tuple[str, ...]
    status: CandidateStatus
    reason: str
    fit_operations_attempted: int
    completed_ns: int

    def _normalize(self) -> None:
        for n in ("preprocessing_ids", "forecast_ids"):
            require(
                len(set(getattr(self, n))) == len(getattr(self, n)), "duplicate fit witness"
            )
            object.__setattr__(self, n, tuple(sorted(getattr(self, n))))

    def _validate(self) -> None:
        for i in (
            self.candidate_id,
            self.model_id,
            *self.preprocessing_ids,
            *self.forecast_ids,
        ):
            if i:
                validate_fingerprint(i)
        require(
            0 <= self.fit_operations_attempted <= 32
            and len(self.forecast_ids) <= 2000
            and len(self.preprocessing_ids) <= 32
            and len(self.reason) <= 256,
            "fit witness bounds",
        )
        require(
            (self.status is CandidateStatus.VALID)
            == (self.model_id is not None and bool(self.forecast_ids)),
            "fit result availability shape",
        )


@contract("sel_pair")
@dataclass(frozen=True, slots=True)
class CandidateValidationPair(Artifact):
    sample_id: str
    truth_id: str
    forecast_id: str
    prediction: float
    truth: float
    primary_loss: float | None

    def _validate(self) -> None:
        for i in (self.sample_id, self.truth_id, self.forecast_id):
            validate_fingerprint(i)


@contract("sel_validation")
@dataclass(frozen=True, slots=True)
class CandidateValidationResult(Artifact):
    candidate_id: str
    fit_id: str
    criterion: SelectionCriterion
    value: float | None
    secondary_value: float | None
    status: CandidateStatus
    reason: str
    declared_sample_ids: tuple[str, ...]
    pairs: tuple[CandidateValidationPair, ...]
    exclusions: tuple[tuple[str, str], ...]
    truth_cutoff_ns: int
    available_ns: int
    trial_id: str

    def _normalize(self) -> None:
        self.ordered("pairs", "sample_id")
        object.__setattr__(self, "declared_sample_ids", tuple(sorted(self.declared_sample_ids)))
        object.__setattr__(self, "exclusions", tuple(sorted(self.exclusions)))

    def _validate(self) -> None:
        for i in (self.candidate_id, self.fit_id, self.trial_id, *self.declared_sample_ids):
            validate_fingerprint(i)
        require(
            len(set(self.declared_sample_ids)) == len(self.declared_sample_ids) <= 2000
            and len(self.pairs) <= 2000
            and len(self.exclusions) <= 2000
            and len({i for i, _ in self.exclusions}) == len(self.exclusions)
            and {p.sample_id for p in self.pairs}.isdisjoint(i for i, _ in self.exclusions)
            and {p.sample_id for p in self.pairs} | {i for i, _ in self.exclusions}
            == set(self.declared_sample_ids),
            "exact validation support/exclusions",
        )
        require(
            self.truth_cutoff_ns <= self.available_ns
            and len(self.reason) <= 256
            and (self.status is CandidateStatus.VALID) == (self.value is not None),
            "validation availability/state",
        )


@contract("sel_result")
@dataclass(frozen=True, slots=True)
class SelectionResult(Artifact):
    request_id: str
    search_space_id: str
    family_plan_id: str
    candidate_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]
    ordering: tuple[str, ...]
    selected_candidate_id: str | None
    selected_model_id: str | None
    criterion: SelectionCriterion
    status: SelectionStatus
    selection_cutoff_ns: int
    available_ns: int
    multiple_testing_family_id: str
    multiple_testing_event_id: str | None
    event_status: str
    usage: ResourceUsage
    exhaustive: bool = True

    def _normalize(self) -> None:
        for n in ("candidate_ids", "validation_ids"):
            object.__setattr__(self, n, tuple(sorted(getattr(self, n))))

    def _validate(self) -> None:
        for i in (
            self.request_id,
            self.search_space_id,
            self.family_plan_id,
            self.selected_candidate_id,
            self.selected_model_id,
            self.multiple_testing_family_id,
            self.multiple_testing_event_id,
            *self.candidate_ids,
            *self.validation_ids,
        ):
            if i:
                validate_fingerprint(i)
        require(
            set(self.ordering) == set(self.candidate_ids)
            and len(self.ordering) == len(set(self.ordering)) == len(self.validation_ids) <= 128
            and len(set(self.validation_ids)) == len(self.validation_ids),
            "complete selection roster",
        )
        require(
            self.selected_candidate_id is None
            or self.selected_candidate_id in self.candidate_ids,
            "winner belongs to roster",
        )
        require(
            (self.status is SelectionStatus.NO_VALID_CANDIDATE)
            == (self.selected_candidate_id is None and self.selected_model_id is None)
            and self.selection_cutoff_ns <= self.available_ns
            and self.exhaustive,
            "exhaustive selection state/clocks",
        )
        require(
            self.event_status
            in (
                "EXACT_NATIVE_EVENT",
                "INCOMPATIBLE_NATIVE_MEDIAN_PROTOCOL",
                "NO_VALID_CANDIDATE",
            )
            and (self.multiple_testing_event_id is not None)
            == (self.event_status == "EXACT_NATIVE_EVENT"),
            "honest native selection event",
        )
