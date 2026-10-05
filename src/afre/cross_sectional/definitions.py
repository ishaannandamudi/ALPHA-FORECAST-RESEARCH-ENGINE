"""Exact origin context, score semantics and explicitly supplied peer policies."""

from dataclasses import dataclass

from afre.cross_sectional.schema import (
    IMPLEMENTATION_VERSION,
    GroupType,
    MissingScorePolicy,
    PeerTransform,
    RankDirection,
    RankingLayer,
    RankTiePolicy,
    ScoreSource,
    SmallGroupPolicy,
)
from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.probabilistic.definitions import ThresholdRequest
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition


@contract("cs_origin")
@dataclass(frozen=True, slots=True)
class CrossSectionIdentity(Artifact):
    anchor_origin: ForecastOrigin
    snapshot_id: str
    target: TargetDefinition
    eligibility_policy_id: str
    security_order: str = "stable-security-fingerprint-v1"

    def _validate(self) -> None:
        validate_fingerprint(self.snapshot_id, "u_snapshot")
        validate_fingerprint(self.eligibility_policy_id, "u_eligibility_policy")
        require(self.security_order == "stable-security-fingerprint-v1", "security ordering")


def origin_context(origin: ForecastOrigin) -> tuple[int, int, str, str, str]:
    """All ForecastOrigin information fields except the security dimension."""
    return (
        origin.timestamp_ns,
        origin.availability_cutoff_ns,
        origin.market_session_id,
        origin.build_context,
        origin.universe_id,
    )


@contract("cs_score_spec")
@dataclass(frozen=True, slots=True)
class ScoreSpec(Artifact):
    source: ScoreSource
    model_id: str | None = None
    calibrated: bool = False
    quantile: float | None = None
    event: ThresholdRequest | None = None
    provider_name: str | None = None
    provider_version: str | None = None
    provider_schema: str | None = None
    signal_name: str | None = None
    signal_version: str | None = None
    signal_semantics: str | None = None
    unit: str | None = None
    maximum_age_ns: int | None = None

    def _validate(self) -> None:
        external = self.source is ScoreSource.EXTERNAL_SIGNAL
        fields = (
            self.provider_name,
            self.provider_version,
            self.provider_schema,
            self.signal_name,
            self.signal_version,
            self.signal_semantics,
            self.unit,
        )
        require(all((v is not None) == external for v in fields), "external score identity")
        require((self.model_id is None) == external, "score model/provider identity")
        if self.model_id is not None:
            validate_fingerprint(self.model_id)
            expected = (
                "afre.c_state:"
                if self.calibrated
                else "afre.m_artifact:"
                if self.source is ScoreSource.POINT_PREDICTION
                else "afre.p_artifact:"
            )
            require(
                self.model_id.startswith((expected, "afre.cs_model:"))
                if self.source is ScoreSource.POINT_PREDICTION
                else self.model_id.startswith(expected),
                "score model family",
            )
        require(
            not self.calibrated
            or self.source
            in (
                ScoreSource.POINT_EXPECTATION,
                ScoreSource.MEDIAN,
                ScoreSource.QUANTILE,
                ScoreSource.THRESHOLD_PROBABILITY,
            ),
            "calibrated score source",
        )
        require(
            (self.quantile is not None) == (self.source is ScoreSource.QUANTILE),
            "quantile score needs exact level",
        )
        require(self.quantile is None or 0 < self.quantile < 1, "score quantile")
        require(
            (self.event is not None) == (self.source is ScoreSource.THRESHOLD_PROBABILITY),
            "event score needs exact comparison/threshold",
        )
        require(self.maximum_age_ns is None or external, "age bound is for external signal")


@contract("cs_normalization_policy")
@dataclass(frozen=True, slots=True)
class NormalizationPolicy(Artifact):
    transform: PeerTransform = PeerTransform.NONE
    sample_denominator: bool = False
    mad_scale: float = 1.0
    minimum_count: int = 2
    zero_scale: str = "explicit-zero"
    percentile_convention: str = "one-minus-rank-minus-one-over-n-minus-one-v1"

    def _validate(self) -> None:
        require(self.minimum_count >= 2 and self.mad_scale > 0, "peer normalization policy")
        require(
            self.transform is PeerTransform.ZSCORE or not self.sample_denominator,
            "sample denominator applies only to zscore",
        )
        require(
            self.transform is PeerTransform.MEDIAN_MAD or self.mad_scale == 1.0,
            "MAD scale applies only to robust normalization",
        )
        require(
            self.zero_scale == "explicit-zero"
            and self.percentile_convention == "one-minus-rank-minus-one-over-n-minus-one-v1",
            "normalization convention",
        )


@contract("cs_group_policy")
@dataclass(frozen=True, slots=True)
class GroupPolicy(Artifact):
    group_type: GroupType
    provider: str
    taxonomy: str
    version: str
    minimum_count: int = 2
    small_group: SmallGroupPolicy = SmallGroupPolicy.MARK_UNAVAILABLE
    method: str = "group-demean-v1"

    def _validate(self) -> None:
        require(
            self.minimum_count >= 2 and self.method == "group-demean-v1",
            "group neutralization policy",
        )


@contract("cs_spec")
@dataclass(frozen=True, slots=True)
class CrossSectionSpec(Artifact):
    identity: CrossSectionIdentity
    score: ScoreSpec
    direction: RankDirection = RankDirection.HIGHER_BETTER
    ties: RankTiePolicy = RankTiePolicy.AVERAGE_RANK
    normalization: NormalizationPolicy = NormalizationPolicy()
    missing: MissingScorePolicy = MissingScorePolicy.EXCLUDE_MISSING
    maximum_missing_fraction: float = 1.0
    group: GroupPolicy | None = None
    ranking_layer: RankingLayer = RankingLayer.RAW
    membership_rule: str = "included-and-eligible-v1"
    implementation_version: str = IMPLEMENTATION_VERSION
    approved_delivery_attestors: tuple[str, ...] = ()

    def _normalize(self) -> None:
        require(
            len(set(self.approved_delivery_attestors)) == len(self.approved_delivery_attestors),
            "duplicate delivery attestor",
        )
        object.__setattr__(
            self, "approved_delivery_attestors", tuple(sorted(self.approved_delivery_attestors))
        )

    def _validate(self) -> None:
        require(0 <= self.maximum_missing_fraction <= 1, "missingness fraction")
        require(
            self.ranking_layer is not RankingLayer.GROUP_NEUTRAL or self.group is not None,
            "group ranking needs group policy",
        )
        require(
            self.membership_rule == "included-and-eligible-v1"
            and self.implementation_version == IMPLEMENTATION_VERSION,
            "unsupported cross-section implementation",
        )
