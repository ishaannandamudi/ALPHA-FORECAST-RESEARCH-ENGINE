"""Complete canonical ordering, predeclared lexicographic metrics and support policy."""

from afre.schema import require
from afre.selection.definitions import SearchSpace
from afre.selection.results import CandidateValidationResult
from afre.selection.schema import CandidateStatus, SelectionStatus


def ordering_for(
    space: SearchSpace, results: tuple[CandidateValidationResult, ...]
) -> tuple[str, ...]:
    valid = [r for r in results if r.status is CandidateStatus.VALID]
    require(
        len({tuple((p.sample_id, p.truth_id) for p in r.pairs) for r in valid}) <= 1,
        "selection ranking requires exact matched VALIDATION sample/truth support",
    )

    def key(r: CandidateValidationResult) -> tuple[bool, float, float, str]:
        return (
            r.status is not CandidateStatus.VALID,
            (-r.value if space.criterion.maximize else r.value) if r.value is not None else 0.0,
            (
                -r.secondary_value
                if space.secondary_criterion and space.secondary_criterion.maximize
                else r.secondary_value
            )
            if r.secondary_value is not None
            else 0.0,
            r.candidate_id,
        )

    return tuple(r.candidate_id for r in sorted(results, key=key))


def winner_for(
    space: SearchSpace, results: tuple[CandidateValidationResult, ...]
) -> tuple[str | None, SelectionStatus]:
    valid = [r for r in results if r.status is CandidateStatus.VALID]
    if not valid or len(valid) == 1 and not space.permit_single_valid:
        return None, SelectionStatus.NO_VALID_CANDIDATE
    return ordering_for(space, results)[0], SelectionStatus.NONCOMPETITIVE if len(
        valid
    ) == 1 else SelectionStatus.COMPETITIVE
