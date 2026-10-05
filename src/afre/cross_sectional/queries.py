"""Bounded indexed provider lookups; callers freeze the selected exact references."""

from typing import TYPE_CHECKING

from afre.cross_sectional.definitions import GroupPolicy, ScoreSpec
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.groups import GroupMembership
from afre.cross_sectional.schema import ScoreSource
from afre.schema import require
from afre.universe.identity import StableSecurityId

if TYPE_CHECKING:
    from afre.cross_sectional.repository import CrossSectionRepository


def external_as_of(
    repo: "CrossSectionRepository",
    score: ScoreSpec,
    security: StableSecurityId,
    at_ns: int,
    cutoff_ns: int,
) -> ExternalSignal | None:
    require(score.source is ScoreSource.EXTERNAL_SIGNAL, "external lookup needs external spec")
    b = repo.cross_section_bounds.external_signals
    rows = repo._connection.execute(
        "SELECT fingerprint FROM cs_records WHERE provider=? AND score_source=? "
        "AND security_id=? "
        "AND origin_ns<=? AND available_ns<=? "
        "ORDER BY origin_ns DESC,available_ns DESC,fingerprint LIMIT ?",
        (score.provider_name, score.signal_name, security.fingerprint, at_ns, cutoff_ns, b + 1),
    ).fetchall()
    require(len(rows) <= b, "external signal lookup bound")
    key = (
        score.provider_name,
        score.provider_version,
        score.provider_schema,
        score.signal_name,
        score.signal_version,
        score.signal_semantics,
        score.unit,
    )
    values = tuple(
        s for row in rows if (s := repo.resolve(ExternalSignal, row[0])).semantic_key == key
    )
    if not values:
        return None
    first = values[0]
    require(
        sum(
            (s.as_of_ns, s.clocks.final_available_ns)
            == (first.as_of_ns, first.clocks.final_available_ns)
            for s in values
        )
        == 1,
        "ambiguous external signal vintage; pin exact correction explicitly",
    )
    return first


def group_as_of(
    repo: "CrossSectionRepository",
    policy: GroupPolicy,
    security: StableSecurityId,
    at_ns: int,
    cutoff_ns: int,
) -> GroupMembership | None:
    b = repo.cross_section_bounds.external_signals
    rows = repo._connection.execute(
        "SELECT fingerprint FROM cs_records WHERE provider=? AND security_id=? "
        "AND group_id IS NOT NULL "
        "AND origin_ns<=? AND available_ns<=? ORDER BY available_ns DESC,fingerprint LIMIT ?",
        (policy.provider, security.fingerprint, at_ns, cutoff_ns, b + 1),
    ).fetchall()
    require(len(rows) <= b, "group history lookup bound")
    values = tuple(
        g
        for row in rows
        if (g := repo.resolve(GroupMembership, row[0])).matches(policy, at_ns, cutoff_ns)
    )
    if not values:
        return None
    require(
        sum(g.clocks.final_available_ns == values[0].clocks.final_available_ns for g in values)
        == 1,
        "ambiguous group vintage; pin exact correction explicitly",
    )
    return values[0]
