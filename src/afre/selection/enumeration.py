"""Fully bound Cartesian product, ordered by immutable candidate identity."""

from afre.selection.definitions import CandidateSpec, SearchSpace


def enumerate_candidates(space: SearchSpace) -> tuple[CandidateSpec, ...]:
    return tuple(
        sorted(
            (
                CandidateSpec(
                    space.fingerprint,
                    r,
                    space.target_id,
                    space.horizon_id,
                    space.dataset_id,
                    space.fold_id,
                )
                for r in space.recipes
            ),
            key=lambda c: c.fingerprint,
        )
    )
