"""Immutable peer state, complete security grid, later truth and diagnostics."""

from dataclasses import dataclass

from afre.cross_sectional.schema import (
    CrossSectionQuality,
    CrossSectionScoreState,
    StabilityMembership,
    TruthPolicy,
)
from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import PointMetric, unique_ids
from afre.universe.identity import ListingId, StableIssuerId, StableSecurityId


@contract("cs_observation")
@dataclass(frozen=True, slots=True)
class CrossSectionObservation(Artifact):
    spec_id: str
    security: StableSecurityId
    origin: ForecastOrigin
    source_id: str | None
    group_id: str | None
    issuer: StableIssuerId | None = None
    listing: ListingId | None = None

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "cs_spec")
        require(self.origin.instrument == self.security.instrument, "observation security")
        if self.source_id is not None:
            validate_fingerprint(self.source_id)
        if self.group_id is not None:
            validate_fingerprint(self.group_id, "cs_group")


@contract("cs_raw_score")
@dataclass(frozen=True, slots=True)
class RawScore(Artifact):
    observation_id: str
    security: StableSecurityId
    value: float | None
    state: CrossSectionScoreState
    available_ns: int | None
    reason: str

    def _validate(self) -> None:
        validate_fingerprint(self.observation_id, "cs_observation")
        require(
            (self.value is not None) == (self.state is CrossSectionScoreState.AVAILABLE),
            "raw score state",
        )
        require(self.value is None or self.available_ns is not None, "raw score availability")


@contract("cs_peer_state")
@dataclass(frozen=True, slots=True)
class PeerState(Artifact):
    spec_id: str
    raw_ids: tuple[str, ...]
    values: tuple[tuple[str, float], ...]
    center: float | None
    scale: float | None
    group_statistics: tuple[tuple[str, int, float | None], ...]
    unavailable_ids: tuple[str, ...]
    quality: CrossSectionQuality
    available_ns: int
    group_neutral: bool

    def _normalize(self) -> None:
        for name in ("raw_ids", "unavailable_ids", "group_statistics", "values"):
            object.__setattr__(self, name, tuple(sorted(getattr(self, name))))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "cs_spec")
        unique_ids(self.raw_ids, "cs_raw_score")
        unique_ids(self.unavailable_ids, "u_security_id")
        unique_ids(tuple(s for s, _ in self.values), "u_security_id")
        require(self.scale is None or self.scale >= 0, "peer scale")


@contract("cs_rank_entry")
@dataclass(frozen=True, slots=True)
class RankEntry(Artifact):
    security: StableSecurityId
    observation_id: str
    raw_id: str
    raw: float | None
    normalized: float | None
    group_neutral: float | None
    rank: float | None
    percentile: float | None
    state: CrossSectionScoreState
    reason: str

    def _validate(self) -> None:
        validate_fingerprint(self.observation_id, "cs_observation")
        validate_fingerprint(self.raw_id, "cs_raw_score")
        require((self.rank is not None) == (self.percentile is not None), "partial rank")
        require(self.percentile is None or 0 <= self.percentile <= 1, "percentile range")
        require(self.rank is None or self.rank >= 1, "rank range")


@contract("cs_ranking")
@dataclass(frozen=True, slots=True)
class CrossSectionRanking(Artifact):
    spec_id: str
    entries: tuple[RankEntry, ...]
    normalization_id: str
    group_neutral_id: str | None
    eligible_count: int
    ranked_count: int
    coverage: float
    quality: CrossSectionQuality
    computed_ns: int
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(
            self, "entries", tuple(sorted(self.entries, key=lambda e: e.security.fingerprint))
        )

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "cs_spec")
        validate_fingerprint(self.normalization_id, "cs_peer_state")
        if self.group_neutral_id is not None:
            validate_fingerprint(self.group_neutral_id, "cs_peer_state")
        require(
            self.eligible_count == len(self.entries)
            and len({e.security for e in self.entries}) == len(self.entries)
            and self.ranked_count == sum(e.rank is not None for e in self.entries)
            and self.coverage
            == (self.ranked_count / self.eligible_count if self.eligible_count else 0.0),
            "rank coverage grid",
        )
        require(self.available_ns >= self.computed_ns, "ranking clocks")


@contract("cs_truth_row")
@dataclass(frozen=True, slots=True)
class TruthRow(Artifact):
    security: StableSecurityId
    target_id: str | None
    sample_id: str | None
    value: float | None
    realized_rank: float | None
    reason: str

    def _validate(self) -> None:
        if self.target_id is not None:
            validate_fingerprint(self.target_id, "target_vintage")
        if self.sample_id is not None:
            validate_fingerprint(self.sample_id, "r_sample")
        require(self.value is None or self.target_id is not None, "truth evidence")


@contract("cs_truth")
@dataclass(frozen=True, slots=True)
class CrossSectionTruth(Artifact):
    ranking_id: str
    rows: tuple[TruthRow, ...]
    policy: TruthPolicy
    cutoff_ns: int
    available_ns: int
    test_evaluation_ids: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(
            self, "rows", tuple(sorted(self.rows, key=lambda r: r.security.fingerprint))
        )
        object.__setattr__(self, "test_evaluation_ids", tuple(sorted(self.test_evaluation_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.ranking_id, "cs_ranking")
        unique_ids(tuple(r.security.fingerprint for r in self.rows), "u_security_id")
        unique_ids(self.test_evaluation_ids, "r_test_evaluation")
        require(self.available_ns >= self.cutoff_ns, "truth computation clocks")


@contract("cs_bucket")
@dataclass(frozen=True, slots=True)
class ScoreBucket(Artifact):
    ordinal: int
    securities: tuple[str, ...]
    mean_truth: float

    def _validate(self) -> None:
        require(self.ordinal >= 0 and bool(self.securities), "bucket count")
        unique_ids(self.securities, "u_security_id")


@contract("cs_evaluation")
@dataclass(frozen=True, slots=True)
class CrossSectionEvaluation(Artifact):
    ranking_id: str
    truth_id: str
    securities: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]
    pearson: PointMetric
    rank_ic: PointMetric
    group_ic: PointMetric
    group_securities: tuple[str, ...]
    top_k: int
    top_ids: tuple[str, ...]
    bottom_ids: tuple[str, ...]
    top_mean: float | None
    bottom_mean: float | None
    spread: float | None
    bucket_count: int
    buckets: tuple[ScoreBucket, ...]
    monotone_fraction: float | None
    cutoff_ns: int
    available_ns: int
    bucket_convention: str = "stable-id-tie-split-equal-count-v1"

    def _validate(self) -> None:
        validate_fingerprint(self.ranking_id, "cs_ranking")
        validate_fingerprint(self.truth_id, "cs_truth")
        unique_ids(self.securities, "u_security_id")
        require(
            self.top_k > 0
            and self.bucket_count >= 2
            and self.bucket_convention == "stable-id-tie-split-equal-count-v1",
            "evaluation policy",
        )


@contract("cs_ic_series")
@dataclass(frozen=True, slots=True)
class ICSeries(Artifact):
    evaluation_ids: tuple[str, ...]
    rank_ic: bool
    origin_keys: tuple[str, ...]
    total_count: int
    defined_count: int
    mean: float | None
    median: float | None
    population_stddev: float | None
    positive_fraction: float | None

    def _validate(self) -> None:
        unique_ids(self.evaluation_ids, "cs_evaluation")
        unique_ids(self.origin_keys, "cs_origin")
        require(
            self.total_count == len(self.evaluation_ids) == len(self.origin_keys)
            and 0 <= self.defined_count <= self.total_count,
            "IC series counts",
        )


@contract("cs_stability")
@dataclass(frozen=True, slots=True)
class RankStability(Artifact):
    previous_id: str
    current_id: str
    policy: StabilityMembership
    intersection_ids: tuple[str, ...]
    added_ids: tuple[str, ...]
    removed_ids: tuple[str, ...]
    same_members: bool
    same_eligible_members: bool
    eligible_added_ids: tuple[str, ...]
    eligible_removed_ids: tuple[str, ...]
    eligible_membership_turnover: float
    spearman: PointMetric
    top_k: int
    top_overlap_count: int
    top_overlap_fraction: float | None
    membership_turnover: float
    mean_rank_displacement: float | None

    def _validate(self) -> None:
        for value in (self.previous_id, self.current_id):
            validate_fingerprint(value, "cs_ranking")
        require(self.top_k > 0 and 0 <= self.membership_turnover <= 1, "stability policy")


@contract("cs_audit")
@dataclass(frozen=True, slots=True)
class CrossSectionAudit(Artifact):
    root_id: str
    evidence_ids: tuple[str, ...]
    checks: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "evidence_ids", tuple(sorted(self.evidence_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.root_id)
        unique_ids(self.evidence_ids)
        require(self.root_id in self.evidence_ids, "audit root")
