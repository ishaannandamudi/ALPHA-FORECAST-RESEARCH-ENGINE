"""Record a caller-supplied selection event; never return a model promotion command."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.multiple_testing.schema import DescriptiveSelectionRule, EvidenceState, ids
from afre.schema import Artifact, contract, require


@contract("mt_selection")
@dataclass(frozen=True, slots=True)
class SelectionEvent(Artifact):
    candidate_trial_ids: tuple[str, ...]
    selected_trial_ids: tuple[str, ...]
    rule: DescriptiveSelectionRule
    higher_is_better: bool
    top_k: int
    threshold: float | None
    selection_cutoff_ns: int
    available_ns: int
    ordering: tuple[str, ...] = ()
    test_involved: bool = False
    metric: str = "descriptive-effect-estimate-v1"

    def _normalize(self) -> None:
        ids(self, "candidate_trial_ids", "selected_trial_ids")

    def _validate(self) -> None:
        require(
            set(self.ordering) == set(self.candidate_trial_ids)
            and len(self.ordering) == len(self.candidate_trial_ids),
            "selection pins exact ordering including unavailable candidates",
        )
        require(
            1 <= len(self.candidate_trial_ids) <= 2000
            and set(self.selected_trial_ids) <= set(self.candidate_trial_ids)
            and 1 <= self.top_k <= len(self.candidate_trial_ids),
            "declared selection opportunity set",
        )
        require(
            self.selection_cutoff_ns <= self.available_ns
            and self.metric == "descriptive-effect-estimate-v1",
            "selection clocks/metric",
        )
        require(
            (self.threshold is not None)
            == (self.rule is DescriptiveSelectionRule.DECLARED_THRESHOLD),
            "selection threshold shape",
        )
        require(
            self.rule is not DescriptiveSelectionRule.MAX_METRIC or self.higher_is_better,
            "max metric direction",
        )
        require(
            self.rule is not DescriptiveSelectionRule.MIN_ERROR or not self.higher_is_better,
            "min error direction",
        )


@contract("mt_selection_bias")
@dataclass(frozen=True, slots=True)
class SelectionBiasDiagnostic(Artifact):
    event_id: str
    analysis_id: str
    registry_id: str
    ordering: tuple[str, ...]
    metrics: tuple[tuple[str, float | None], ...]
    candidate_count: int
    winner_metric: float | None
    median_metric: float | None
    winner_minus_median: float | None
    winner_minus_next: float | None
    adjusted_result_ids: tuple[str, ...]
    test_use_count: int
    state: EvidenceState
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "adjusted_result_ids")
        object.__setattr__(self, "metrics", tuple(sorted(self.metrics)))

    def _validate(self) -> None:
        for identity in (self.event_id, self.analysis_id, self.registry_id):
            validate_fingerprint(identity)
        require(
            len(self.ordering)
            == len(set(self.ordering))
            == len(self.metrics)
            == self.candidate_count
            <= 2000,
            "selection diagnostic counts",
        )
