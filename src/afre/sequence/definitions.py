"""Versioned source semantics, explicit causal windows and supplied model settings."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.sequence.schema import (
    SEQUENCE_IMPLEMENTATION,
    SequenceFamily,
    SequencePadding,
    SequencePreprocessing,
    SequenceRevisionPolicy,
    SequenceTimeEncoding,
    SequenceWindowMode,
)
from afre.target_engine.definitions import TargetDefinition


@contract("sq_feature")
@dataclass(frozen=True, slots=True)
class SequenceFeatureDefinition(Artifact):
    source_definition_id: str
    semantic_name: str
    semantic_version: str
    unit: str
    value_type: str = "finite-real"
    missingness_policy: str = "mask-no-fill-v1"
    alignment_policy: str = "exact-timestamp-union-v1"
    availability_policy: str = "source-final-availability-v1"
    transform_policy: str = "declared-TRAIN-standardization-or-none-v1"
    implementation_version: str = SEQUENCE_IMPLEMENTATION

    def _validate(self) -> None:
        require(
            self.source_definition_id.startswith(("afre.nl_feature:", "afre.nl_interaction:")),
            "sequence accepts exact neutral scalar/interaction definitions only",
        )
        validate_fingerprint(self.source_definition_id)
        require(
            self.value_type == "finite-real"
            and self.missingness_policy == "mask-no-fill-v1"
            and self.alignment_policy == "exact-timestamp-union-v1"
            and self.availability_policy == "source-final-availability-v1"
            and self.transform_policy == "declared-TRAIN-standardization-or-none-v1"
            and self.implementation_version == SEQUENCE_IMPLEMENTATION,
            "sequence feature implementation",
        )


@contract("sq_window")
@dataclass(frozen=True, slots=True)
class SequenceWindowSpec(Artifact):
    mode: SequenceWindowMode
    maximum_observations: int
    minimum_observations: int = 1
    duration_ns: int | None = None
    lower_inclusive: bool = False
    upper_inclusive: bool = True
    padding: SequencePadding = SequencePadding.LEFT_PAD_MASKED
    revision_policy: SequenceRevisionPolicy = SequenceRevisionPolicy.LATEST_AVAILABLE_REVISION
    exact_observation_ids: tuple[str, ...] = ()
    time_encoding: SequenceTimeEncoding = SequenceTimeEncoding.DELTA_SECONDS
    anchor: str = "forecast-origin-availability-cutoff-v1"
    alignment: str = "exact-timestamp-union-v1"
    ordering: str = "observation-time-availability-source-identity-v1"
    calendar_semantics: str = "elapsed-UTC-no-session-inference-v1"
    implementation_version: str = SEQUENCE_IMPLEMENTATION

    def _normalize(self) -> None:
        object.__setattr__(
            self, "exact_observation_ids", tuple(sorted(self.exact_observation_ids))
        )

    def _validate(self) -> None:
        require(
            1 <= self.minimum_observations <= self.maximum_observations <= 128,
            "sequence window length bounds",
        )
        require(
            (self.duration_ns is not None) == (self.mode is SequenceWindowMode.ELAPSED_DURATION)
            and (self.duration_ns is None or self.duration_ns > 0),
            "window duration mode",
        )
        require(
            (bool(self.exact_observation_ids))
            == (self.revision_policy is SequenceRevisionPolicy.EXACT_VINTAGE),
            "exact vintage roster",
        )
        require(
            len(self.exact_observation_ids) <= 100_000
            and len(set(self.exact_observation_ids)) == len(self.exact_observation_ids),
            "duplicate exact vintages",
        )
        for identity in self.exact_observation_ids:
            validate_fingerprint(identity, "sq_observation")
        require(
            self.anchor == "forecast-origin-availability-cutoff-v1"
            and self.alignment == "exact-timestamp-union-v1"
            and self.ordering == "observation-time-availability-source-identity-v1"
            and self.calendar_semantics == "elapsed-UTC-no-session-inference-v1"
            and self.implementation_version == SEQUENCE_IMPLEMENTATION,
            "window implementation",
        )


@contract("sq_spec")
@dataclass(frozen=True, slots=True)
class SequenceModelSpec(Artifact):
    target: TargetDefinition
    features: tuple[SequenceFeatureDefinition, ...]
    window: SequenceWindowSpec
    family: SequenceFamily
    fold_id: str
    cutoff_ns: int
    seed: int
    preprocessing: SequencePreprocessing = SequencePreprocessing.NONE
    decay_rate_per_second: float = 0.0
    state_transition: float = 0.5
    state_input_gain: float = 1.0
    ridge_penalty: float = 0.0
    tolerance: float = 1e-12
    condition_limit: float = 1e12
    approved_delivery_attestors: tuple[str, ...] = ()
    missing_model_policy: str = "require-one-unmasked-value-per-feature-v1"
    state_mask_policy: str = "skip-masked-feature-update-zero-initial-state-v1"
    optimizer: str = "AFRE5-pivoted-QR-fixed-readout-v1"
    implementation_version: str = SEQUENCE_IMPLEMENTATION

    def _normalize(self) -> None:
        self.ordered("features", "fingerprint")
        object.__setattr__(
            self, "approved_delivery_attestors", tuple(sorted(self.approved_delivery_attestors))
        )

    def _validate(self) -> None:
        validate_fingerprint(self.fold_id, "r_fold")
        require(
            1 <= len(self.features) <= 16
            and len({f.source_definition_id for f in self.features}) == len(self.features),
            "unique bounded sequence features",
        )
        require(
            0 <= self.seed < 2**32
            and self.decay_rate_per_second >= 0
            and -1 < self.state_transition < 1
            and self.state_input_gain > 0
            and self.ridge_penalty >= 0
            and 0 < self.tolerance < 1
            and self.condition_limit >= 1,
            "sequence fixed numerical policy",
        )
        require(
            len(set(self.approved_delivery_attestors)) == len(self.approved_delivery_attestors),
            "duplicate sequence attestors",
        )
        require(
            self.missing_model_policy == "require-one-unmasked-value-per-feature-v1"
            and self.state_mask_policy == "skip-masked-feature-update-zero-initial-state-v1"
            and self.optimizer == "AFRE5-pivoted-QR-fixed-readout-v1"
            and self.implementation_version == SEQUENCE_IMPLEMENTATION,
            "sequence model implementation",
        )
