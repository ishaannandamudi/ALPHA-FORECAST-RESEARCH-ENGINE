"""Exact full-origin/sample/fold alignment, no independent pairwise deletion."""

from typing import TYPE_CHECKING

from afre.orthogonalization.artifacts import AlignedSignalRow
from afre.orthogonalization.definitions import OrthogonalizationSpec
from afre.orthogonalization.schema import OrthogonalizationMode
from afre.orthogonalization.signals import SignalObservation
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import require

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def row_for(
    repo: "OrthogonalizationRepository", spec: OrthogonalizationSpec, ids: tuple[str, ...]
) -> AlignedSignalRow:
    require(
        len(ids) == len(spec.references) + 1 and len(set(ids)) == len(ids),
        "one candidate and each reference observation required",
    )
    observations = tuple(repo.resolve(SignalObservation, i) for i in ids)
    by_ref = {o.reference_id: o for o in observations}
    refs = (spec.candidate, *spec.references)
    require(set(by_ref) == {r.fingerprint for r in refs}, "aligned exact reference set")
    ordered = tuple(by_ref[r.fingerprint] for r in refs)
    first = ordered[0]
    require(
        all(o.sample_id == first.sample_id and o.origin == first.origin for o in ordered),
        "alignment exact sample/full origin",
    )
    memberships = tuple(
        m for m in repo.fold_memberships(spec.fold_id) if m.sample_id == first.sample_id
    )
    require(
        len(memberships) == 1
        and memberships[0].partition in (Partition.TRAIN, Partition.VALIDATION, Partition.TEST),
        "aligned admitted fold sample",
    )
    sample = repo.resolve(ResearchSample, first.sample_id)
    require(
        sample.target_definition_id == spec.target.fingerprint and not sample.dropped,
        "aligned exact target/horizon and eligibility",
    )
    if spec.mode is OrthogonalizationMode.CROSS_SECTIONAL_HISTORICAL:
        from afre.universe.models import EligibilityResult, UniverseSnapshot
        from afre.universe.schema import EligibilityState
        from afre.universe.validation import to_universe_manifest, validate_snapshot_origin

        eligibility = repo.resolve(EligibilityResult, sample.eligibility_id)
        snapshot = repo.resolve(UniverseSnapshot, sample.snapshot_id)
        require(
            eligibility in snapshot.eligibility
            and eligibility.state is EligibilityState.ELIGIBLE,
            "PIT cross-sectional exact eligible universe",
        )
        validate_snapshot_origin(snapshot, to_universe_manifest(snapshot), first.origin)
    return AlignedSignalRow(
        spec.fingerprint,
        first.sample_id,
        first.origin,
        memberships[0].partition,
        tuple(o.fingerprint for o in ordered),
        first.value,
        tuple(o.value for o in ordered[1:]),
        max(o.available_ns for o in ordered),
    )


def rows_for(
    repo: "OrthogonalizationRepository", spec_id: str, ids: tuple[str, ...]
) -> tuple[AlignedSignalRow, ...]:
    require(
        0 < len(ids) <= repo.orthogonalization_bounds.rows and len(set(ids)) == len(ids),
        "orthogonal row bounds/duplicates",
    )
    rows = tuple(repo.resolve(AlignedSignalRow, i) for i in ids)
    require(
        all(r.spec_id == spec_id for r in rows)
        and len({r.sample_id for r in rows}) == len(rows),
        "exact spec and unique samples",
    )
    return tuple(
        sorted(
            rows,
            key=lambda r: (r.origin.timestamp_ns, r.origin.instrument.fingerprint, r.sample_id),
        )
    )


def complete(row: AlignedSignalRow) -> bool:
    return row.candidate is not None and all(v is not None for v in row.references)


def validate_cross_sectional_grid(
    repo: "OrthogonalizationRepository", rows: tuple[AlignedSignalRow, ...]
) -> None:
    from afre.cross_sectional.definitions import origin_context
    from afre.universe.models import UniverseSnapshot
    from afre.universe.schema import EligibilityState

    spec = repo.resolve(OrthogonalizationSpec, rows[0].spec_id)
    if spec.mode is not OrthogonalizationMode.CROSS_SECTIONAL_HISTORICAL:
        return
    groups: dict[tuple[object, ...], list[AlignedSignalRow]] = {}
    for row in rows:
        groups.setdefault(origin_context(row.origin), []).append(row)
    require(
        len(groups) == len({row.origin.timestamp_ns for row in rows}),
        "cross-sectional one full universe/origin context per timestamp",
    )
    for group in groups.values():
        samples = tuple(repo.resolve(ResearchSample, r.sample_id) for r in group)
        require(len({s.snapshot_id for s in samples}) == 1, "cross-sectional exact snapshot")
        snapshot = repo.resolve(UniverseSnapshot, samples[0].snapshot_id)
        expected = {
            e.membership.security.instrument
            for e in snapshot.eligibility
            if e.state is EligibilityState.ELIGIBLE
        }
        require(
            {r.origin.instrument for r in group} == expected and len(group) == len(expected),
            "cross-sectional complete same-origin eligible grid",
        )
