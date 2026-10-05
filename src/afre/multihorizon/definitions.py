"""Supplied architecture, exact model mappings and complete sharing declaration."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.multihorizon.horizon_sets import HorizonSet
from afre.multihorizon.schema import IMPLEMENTATION_VERSION, Architecture, ParameterOwnership
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import unique_ids


@contract("mh_binding")
@dataclass(frozen=True, slots=True)
class HorizonModelBinding(Artifact):
    target_definition_id: str
    feature_set_id: str
    point_spec_id: str
    point_model_id: str
    fold_id: str
    training_cutoff_ns: int
    preprocessing_state_ids: tuple[str, ...]
    probability_spec_id: str | None = None
    probability_model_id: str | None = None
    calibration_spec_id: str | None = None
    calibration_state_id: str | None = None

    def _validate(self) -> None:
        for identity, domain in (
            (self.target_definition_id, "target_definition"),
            (self.feature_set_id, "fs_feature_set"),
            (self.point_spec_id, "m_spec"),
            (self.point_model_id, "m_artifact"),
            (self.fold_id, "r_fold"),
        ):
            validate_fingerprint(identity, domain)
        unique_ids(self.preprocessing_state_ids, "r_preprocessing_state")
        for spec, model, sd, md in (
            (self.probability_spec_id, self.probability_model_id, "p_spec", "p_artifact"),
            (self.calibration_spec_id, self.calibration_state_id, "c_spec", "c_state"),
        ):
            require((spec is None) == (model is None), "incomplete layer binding")
            if spec is not None and model is not None:
                validate_fingerprint(spec, sd)
                validate_fingerprint(model, md)
        require(
            self.calibration_state_id is None or self.probability_model_id is not None,
            "calibration requires probability layer",
        )


@contract("mh_sharing")
@dataclass(frozen=True, slots=True)
class ParameterSharing(Artifact):
    parameter: str
    ownership: ParameterOwnership
    target_ids: tuple[str, ...]
    version: str = "ownership-v1"

    def _normalize(self) -> None:
        object.__setattr__(self, "target_ids", tuple(sorted(self.target_ids)))

    def _validate(self) -> None:
        unique_ids(self.target_ids, "target_definition")
        require(bool(self.target_ids) and self.version == "ownership-v1", "sharing declaration")
        require(
            self.ownership is not ParameterOwnership.HORIZON_SPECIFIC
            or len(self.target_ids) == 1,
            "horizon-specific ownership cardinality",
        )
        require(
            self.ownership is not ParameterOwnership.GROUP_SHARED or len(self.target_ids) > 1,
            "shared group cardinality",
        )


@contract("mh_model_spec")
@dataclass(frozen=True, slots=True)
class MultiHorizonModelSpec(Artifact):
    horizon_set: HorizonSet
    architecture: Architecture
    bindings: tuple[HorizonModelBinding, ...]
    sharing: tuple[ParameterSharing, ...]
    horizon_weights: tuple[float, ...]
    random_seed: int = 0
    shared_cutoff_ns: int | None = None
    ridge_penalty: float = 0.0
    tolerance: float = 1e-12
    condition_limit: float = 1e12
    loss_policy: str = "declared-weighted-squared-sum-v1"
    implementation_version: str = IMPLEMENTATION_VERSION

    def _normalize(self) -> None:
        lookup = {b.target_definition_id: b for b in self.bindings}
        require(
            len(lookup) == len(self.bindings)
            and set(lookup) == {t.fingerprint for t in self.horizon_set.targets},
            "exact one model binding per horizon",
        )
        object.__setattr__(
            self, "bindings", tuple(lookup[t.fingerprint] for t in self.horizon_set.targets)
        )
        self.ordered("sharing", "fingerprint")

    def _validate(self) -> None:
        ids = {t.fingerprint for t in self.horizon_set.targets}
        require(
            len(self.horizon_weights) == len(ids)
            and all(w >= 0 for w in self.horizon_weights)
            and sum(self.horizon_weights) > 0,
            "explicit nonnegative horizon weights",
        )
        require(
            0 <= self.random_seed < 2**64
            and self.ridge_penalty >= 0
            and 0 < self.tolerance < 1
            and self.condition_limit >= 1,
            "shared numerical policy",
        )
        require(
            self.loss_policy == "declared-weighted-squared-sum-v1"
            and self.implementation_version == IMPLEMENTATION_VERSION,
            "architecture version",
        )
        require(
            all(set(s.target_ids) <= ids for s in self.sharing), "sharing outside horizon set"
        )
        if self.architecture is not Architecture.INDEPENDENT_PER_HORIZON:
            require(
                len({b.feature_set_id for b in self.bindings}) == 1,
                "shared architecture requires same exact features",
            )
        expected = []
        for parameter in ("coefficients", "intercept", "transforms", "scale", "calibration"):
            if (
                parameter == "coefficients"
                and self.architecture is Architecture.SHARED_LINEAR_BACKBONE
            ):
                expected.append(
                    ParameterSharing(parameter, ParameterOwnership.GLOBAL_SHARED, tuple(ids))
                )
            else:
                expected.extend(
                    ParameterSharing(
                        parameter, ParameterOwnership.HORIZON_SPECIFIC, (identity,)
                    )
                    for identity in ids
                )
        require(set(expected) == set(self.sharing), "complete supported sharing map required")
        if self.architecture is Architecture.SHARED_LINEAR_BACKBONE:
            require(
                self.shared_cutoff_ns is not None
                and all(self.shared_cutoff_ns <= b.training_cutoff_ns for b in self.bindings),
                "shared cutoff exceeds horizon cutoff",
            )
            require(
                all(w > 0 for w in self.horizon_weights), "shared outputs need positive weights"
            )
            require(
                len({b.preprocessing_state_ids for b in self.bindings}) == 1
                and all(b.probability_model_id is None for b in self.bindings),
                (
                    "backbone point layer requires equal supplied transforms; "
                    "separate uncertainty unsupported"
                ),
            )
        else:
            require(
                self.shared_cutoff_ns is None and self.ridge_penalty == 0,
                "independent architecture has no shared fit policy",
            )


def sharing_for(
    horizons: HorizonSet, architecture: Architecture
) -> tuple[ParameterSharing, ...]:
    ids = tuple(t.fingerprint for t in horizons.targets)
    return tuple(
        s
        for p in ("coefficients", "intercept", "transforms", "scale", "calibration")
        for s in (
            (ParameterSharing(p, ParameterOwnership.GLOBAL_SHARED, ids),)
            if p == "coefficients" and architecture is Architecture.SHARED_LINEAR_BACKBONE
            else tuple(
                ParameterSharing(p, ParameterOwnership.HORIZON_SPECIFIC, (i,)) for i in ids
            )
        )
    )
