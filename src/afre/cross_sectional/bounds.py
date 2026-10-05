"""Allocation and serialized output limits before publication."""

from afre.cross_sectional.artifacts import (
    CrossSectionAudit,
    CrossSectionEvaluation,
    CrossSectionRanking,
    CrossSectionTruth,
    ICSeries,
    PeerState,
    RankStability,
)
from afre.cross_sectional.models import CrossSectionModel
from afre.cross_sectional.schema import CrossSectionBounds
from afre.schema import Artifact, require
from afre.serialization import canonical_json


def check_bounds(value: Artifact, b: CrossSectionBounds) -> None:
    if isinstance(value, CrossSectionRanking):
        require(len(value.entries) <= b.securities, "ranking security bound")
    elif isinstance(value, PeerState):
        require(
            len(value.raw_ids) <= b.securities and len(value.group_statistics) <= b.groups,
            "peer security/group bound",
        )
    elif isinstance(value, CrossSectionTruth):
        require(len(value.rows) <= min(b.securities, b.truths), "truth security bound")
    elif isinstance(value, CrossSectionEvaluation):
        require(
            len(value.securities) + len(value.excluded) <= b.securities,
            "evaluation security bound",
        )
    elif isinstance(value, CrossSectionModel):
        require(
            len(value.feature_ids) <= b.features
            and sum(len(g) for g in value.train_groups) <= b.truths,
            "relative model bounds",
        )
    elif isinstance(value, ICSeries):
        require(len(value.evaluation_ids) <= b.series, "IC series bound")
    elif isinstance(value, RankStability):
        require(
            len(value.intersection_ids) + len(value.added_ids) + len(value.removed_ids)
            <= 2 * b.securities,
            "stability security bound",
        )
    elif isinstance(value, CrossSectionAudit):
        require(len(value.evidence_ids) <= b.audit_nodes, "cross-section audit bound")
    require(
        len(canonical_json(value).encode()) <= b.serialized_bytes, "cross-section byte bound"
    )
