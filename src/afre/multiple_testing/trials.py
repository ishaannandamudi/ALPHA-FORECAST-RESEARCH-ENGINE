"""A planned opportunity and its one append-only completion are separate identities."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.multiple_testing.schema import AdaptiveTrialStatus, TrialState, ids
from afre.schema import Artifact, contract, require


@contract("mt_plan")
@dataclass(frozen=True, slots=True)
class TrialSpecification(Artifact):
    attempt_key: str
    hypothesis_id: str
    native_phase: int
    source_artifact_id: str
    source_ids: tuple[str, ...]
    sample_ids: tuple[str, ...]
    dataset_id: str
    fold_id: str
    preprocessing_ids: tuple[str, ...]
    model_spec_ids: tuple[str, ...]
    choices: tuple[tuple[str, str], ...]
    declared_ns: int
    adaptivity: AdaptiveTrialStatus
    known_trial_ids: tuple[str, ...] = ()
    right_source_ids: tuple[str, ...] = ()
    environment_id: str | None = None
    membership_ids: tuple[str, ...] = ()
    cost_scenario_id: str | None = None
    implementation: str = "exact-native-heldout-source-and-truth-intersection-v1"

    def _normalize(self) -> None:
        ids(
            self,
            "source_ids",
            "sample_ids",
            "preprocessing_ids",
            "model_spec_ids",
            "known_trial_ids",
            "right_source_ids",
            "membership_ids",
        )
        require(
            len(self.choices) <= 32
            and len({n for n, _ in self.choices}) == len(self.choices)
            and all(len(n) <= 128 and len(v) <= 256 for n, v in self.choices),
            "bounded distinct evaluated choices",
        )
        object.__setattr__(self, "choices", tuple(sorted(self.choices)))

    def _validate(self) -> None:
        for identity in (
            self.hypothesis_id,
            self.source_artifact_id,
            self.dataset_id,
            self.fold_id,
            self.environment_id,
            self.cost_scenario_id,
        ):
            if identity:
                validate_fingerprint(identity)
        require(
            5 <= self.native_phase <= 18
            and 1 <= len(self.sample_ids) <= 2000
            and 1 <= len(self.source_ids) <= 2000,
            "native trial source/sample bounds",
        )
        require(
            len(self.right_source_ids) <= 2000
            and len(self.known_trial_ids) <= 2000
            and len(self.membership_ids) <= 2000
            and len(self.attempt_key) <= 128
            and len(self.preprocessing_ids) <= 32
            and len(self.model_spec_ids) <= 32,
            "trial opportunity bounds",
        )
        require(
            (self.environment_id is not None) == bool(self.membership_ids),
            "explicit environment evidence",
        )
        require(
            self.adaptivity is not AdaptiveTrialStatus.PREDECLARED or not self.known_trial_ids,
            "predeclared cannot depend on known trial results",
        )
        require(
            self.adaptivity is not AdaptiveTrialStatus.ADAPTIVE or bool(self.known_trial_ids),
            "adaptive dependencies required",
        )
        require(
            self.implementation == "exact-native-heldout-source-and-truth-intersection-v1",
            "closed trial semantics",
        )


@contract("mt_observation")
@dataclass(frozen=True, slots=True)
class TrialObservation(Artifact):
    sample_id: str
    truth_id: str
    source_id: str
    right_source_id: str | None
    value: float
    unit: str
    native_evaluation_id: str | None = None

    def _validate(self) -> None:
        for identity in (
            self.sample_id,
            self.truth_id,
            self.source_id,
            self.right_source_id,
            self.native_evaluation_id,
        ):
            if identity:
                validate_fingerprint(identity)


@contract("mt_trial")
@dataclass(frozen=True, slots=True)
class ResearchTrial(Artifact):
    plan_id: str
    family_id: str
    hypothesis_id: str
    state: TrialState
    reason: str
    observations: tuple[TrialObservation, ...]
    exclusions: tuple[tuple[str, str], ...]
    native_result_ids: tuple[str, ...]
    test_seal_ids: tuple[str, ...]
    evaluation_cutoff_ns: int
    completed_ns: int
    implementation: str = "registered-one-completion-per-declared-attempt-v1"

    def _normalize(self) -> None:
        ids(self, "native_result_ids", "test_seal_ids")
        self.ordered("observations", "sample_id")
        require(
            len({i for i, _ in self.exclusions}) == len(self.exclusions),
            "duplicate trial exclusions",
        )
        object.__setattr__(self, "exclusions", tuple(sorted(self.exclusions)))

    def _validate(self) -> None:
        for identity in (self.plan_id, self.family_id, self.hypothesis_id):
            validate_fingerprint(identity)
        require(
            self.evaluation_cutoff_ns <= self.completed_ns
            and len(self.observations) <= 2000
            and len(self.exclusions) <= 4000
            and len(self.test_seal_ids) <= 2000
            and len(self.native_result_ids) <= 16,
            "trial completion clocks/bounds",
        )
        require(
            self.state is TrialState.COMPLETED or not self.observations,
            "failed/unavailable trials retain no invented observations",
        )
        require(
            self.implementation == "registered-one-completion-per-declared-attempt-v1",
            "closed trial completion",
        )
