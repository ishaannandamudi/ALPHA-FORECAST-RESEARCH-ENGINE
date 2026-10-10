"""Pinned VALIDATION witnesses, cutoff admissions and frozen metric replay."""

from dataclasses import replace
from typing import TYPE_CHECKING

from afre.probabilistic.artifacts import DistributionParameters
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import ContractError, require
from afre.selection.criteria import loss, metric
from afre.selection.definitions import SearchSpace
from afre.selection.results import (
    CandidateFitResult,
    CandidateValidationPair,
    CandidateValidationResult,
)
from afre.selection.schema import CandidateStatus
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff
from afre.uncertainty.sources import source_for

if TYPE_CHECKING:
    from afre.selection.repository import SelectionRepository


def score_candidate(
    repo: "SelectionRepository",
    space: SearchSpace,
    fit: CandidateFitResult,
    trial_id: str,
    cutoff_ns: int,
    available_ns: int,
    pinned_pairs: tuple[CandidateValidationPair, ...] | None = None,
) -> CandidateValidationResult:
    pairs = []
    secondary = []
    exclusions = []
    status = fit.status
    reason = fit.reason
    if status is CandidateStatus.VALID:
        pinned = {p.sample_id: p.truth_id for p in pinned_pairs or ()}
        try:
            projected = tuple(source_for(repo, i) for i in fit.forecast_ids)
            require(
                {s.sample_id for s in projected} == set(space.validation_sample_ids)
                and len(projected) == len(space.validation_sample_ids),
                "exact VALIDATION candidate source grid",
            )
            for s in sorted(projected, key=lambda s: s.sample_id):
                require(
                    s.partition is Partition.VALIDATION
                    and s.target.fingerprint == space.target_id
                    and s.fold_id == space.fold_id
                    and s.available_ns <= cutoff_ns,
                    "selection exact VALIDATION target/fold/availability",
                )
                sample = repo.resolve(ResearchSample, s.sample_id)
                identity = pinned.get(sample.fingerprint, sample.target_id)
                target = repo.resolve(TargetVintage, identity) if identity else None
                if target is None or not target_known_by_cutoff(target, cutoff_ns):
                    exclusions.append((sample.fingerprint, "truth-unavailable-at-cutoff"))
                    continue
                require(
                    target.origin == s.origin and target.definition == s.target,
                    "exact validation origin/truth",
                )
                assert target.value is not None
                law = s.law if isinstance(s.law, DistributionParameters) else None
                primary = loss(space.criterion, s.prediction, target.value, law)
                pairs.append(
                    CandidateValidationPair(
                        sample.fingerprint,
                        target.fingerprint,
                        s.artifact.fingerprint,
                        s.prediction,
                        target.value,
                        primary,
                    )
                )
                secondary.append(
                    loss(space.secondary_criterion, s.prediction, target.value, law)
                    if space.secondary_criterion
                    else None
                )
            ordered = tuple(pairs)
            value = metric(space.criterion, ordered, tuple(p.primary_loss for p in ordered))
            secondary_value = (
                metric(space.secondary_criterion, ordered, tuple(secondary))
                if space.secondary_criterion
                else None
            )
            if len(pairs) < space.minimum_support:
                status, reason = (
                    CandidateStatus.INSUFFICIENT_DATA,
                    "insufficient-VALIDATION-support",
                )
            elif (
                value is None
                or space.secondary_criterion is not None
                and secondary_value is None
            ):
                status, reason = (
                    CandidateStatus.INCOMPATIBLE,
                    "native-output-or-target-incompatible-with-criterion",
                )
            else:
                status, reason = CandidateStatus.VALID, "exact-native-VALIDATION-score"
        except (ArithmeticError, ContractError) as exc:
            # Repository guard/corruption errors must not be hidden as numeric failure.
            if not isinstance(exc, ArithmeticError) and not any(
                s in str(exc).lower() for s in ("nonfinite", "overflow", "numeric")
            ):
                raise
            status, reason = CandidateStatus.NUMERICAL_FAILURE, "validation-numerical-failure"
            pairs = []
            secondary = []
            exclusions = []
            value = secondary_value = None
    else:
        value = secondary_value = None
    represented = {p.sample_id for p in pairs} | {i for i, _ in exclusions}
    exclusions.extend((i, reason) for i in space.validation_sample_ids if i not in represented)
    result = CandidateValidationResult(
        fit.candidate_id,
        fit.fingerprint,
        space.criterion,
        value if status is CandidateStatus.VALID else None,
        secondary_value if status is CandidateStatus.VALID else None,
        status,
        reason,
        space.validation_sample_ids,
        tuple(pairs),
        tuple(exclusions),
        cutoff_ns,
        available_ns,
        trial_id,
    )
    return replace(result)
