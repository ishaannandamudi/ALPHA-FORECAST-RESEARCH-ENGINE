"""Bounded indexed history with exact provider/taxonomy/subject and causal clocks."""

from typing import TYPE_CHECKING

from afre.regime_conditioned.regimes import RegimeSnapshot, RegimeSubject
from afre.regime_conditioned.schema import RegimeQuality, RegimeStateSemantics
from afre.schema import require

if TYPE_CHECKING:
    from afre.regime_conditioned.repository import RegimeRepository


def snapshots_known(
    repo: "RegimeRepository",
    provider: str,
    taxonomy_id: str,
    subject: RegimeSubject,
    cutoff_ns: int,
) -> tuple[RegimeSnapshot, ...]:
    rows = repo._connection.execute(
        "SELECT fingerprint FROM rc_records WHERE provider=? "
        "AND taxonomy_id=? AND subject_id=? AND as_of_ns<=? AND available_ns<=? "
        "ORDER BY as_of_ns,available_ns,fingerprint LIMIT ?",
        (
            provider,
            taxonomy_id,
            subject.fingerprint,
            cutoff_ns,
            cutoff_ns,
            repo.regime_bounds.snapshots + 1,
        ),
    ).fetchall()
    require(len(rows) <= repo.regime_bounds.snapshots, "regime history query bound")
    return tuple(
        s
        for row in rows
        if (s := repo.resolve(RegimeSnapshot, row[0])).semantics
        is RegimeStateSemantics.FILTERED
        and s.quality is RegimeQuality.VALID
    )
