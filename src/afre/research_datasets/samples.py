"""Compact frozen selections and explicit failed research grid cells."""

from dataclasses import dataclass

from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.research_datasets.definitions import ResearchOriginRequest
from afre.research_datasets.intervals import SampleInformationInterval
from afre.research_datasets.schema import SampleState
from afre.schema import Artifact, contract, require
from afre.universe.identity import StableSecurityId


@contract("r_selection")
@dataclass(frozen=True, slots=True)
class ResearchSelection(Artifact):
    request: ResearchOriginRequest
    security: StableSecurityId
    timestamp_ns: int
    cutoff_ns: int
    origin: ForecastOrigin | None
    eligibility_id: str
    join_id: str | None
    state: SampleState
    group_keys: tuple[tuple[str, str], ...] = ()

    def _normalize(self) -> None:
        require(
            len({x[0] for x in self.group_keys}) == len(self.group_keys),
            "ambiguous sample groups",
        )
        object.__setattr__(self, "group_keys", tuple(sorted(self.group_keys)))

    def _validate(self) -> None:
        validate_fingerprint(self.eligibility_id, "u_eligibility_result")
        require(self.cutoff_ns <= self.timestamp_ns, "sample future knowledge cutoff")
        if self.join_id is not None:
            validate_fingerprint(self.join_id, "fs_join_result")
            require(self.origin is not None, "feature selection without origin")
        if self.origin is not None:
            require(
                self.origin.instrument == self.security.instrument
                and self.origin.timestamp_ns == self.timestamp_ns
                and self.origin.availability_cutoff_ns == self.cutoff_ns,
                "sample/origin mismatch",
            )


@contract("r_sample")
@dataclass(frozen=True, slots=True)
class ResearchSample(Artifact):
    input_build_id: str
    selection_id: str
    security: StableSecurityId
    origin: ForecastOrigin | None
    timestamp_ns: int
    snapshot_id: str
    eligibility_id: str
    feature_set_id: str
    join_id: str | None
    feature_vintage_ids: tuple[str, ...]
    target_definition_id: str
    target_id: str | None
    target_interval: SampleInformationInterval | None
    full_information_interval: SampleInformationInterval | None
    target_available_ns: int | None
    state: SampleState
    dropped: bool
    group_keys: tuple[tuple[str, str], ...]

    def _normalize(self) -> None:
        require(
            len(set(self.feature_vintage_ids)) == len(self.feature_vintage_ids),
            "duplicate selected feature vintage",
        )
        object.__setattr__(self, "feature_vintage_ids", tuple(sorted(self.feature_vintage_ids)))

    def _validate(self) -> None:
        for identity, domain in (
            (self.input_build_id, "r_input_build"),
            (self.selection_id, "r_selection"),
            (self.snapshot_id, "u_snapshot"),
            (self.eligibility_id, "u_eligibility_result"),
            (self.feature_set_id, "fs_feature_set"),
            (self.target_definition_id, "target_definition"),
        ):
            validate_fingerprint(identity, domain)
        for optional_identity, optional_domain in (
            (self.join_id, "fs_join_result"),
            (self.target_id, "target_vintage"),
        ):
            if optional_identity is not None:
                validate_fingerprint(optional_identity, optional_domain)
        for identity in self.feature_vintage_ids:
            validate_fingerprint(identity, "fs_vintage")
        if self.origin is not None:
            require(
                self.origin.instrument == self.security.instrument
                and self.origin.timestamp_ns == self.timestamp_ns,
                "research sample stable origin mismatch",
            )
        require(
            self.state is not SampleState.AVAILABLE
            or (
                self.target_id is not None
                and self.join_id is not None
                and self.target_interval is not None
                and self.full_information_interval is not None
                and bool(self.feature_vintage_ids)
                and self.target_available_ns is not None
            ),
            "available sample lacks exact evidence",
        )
