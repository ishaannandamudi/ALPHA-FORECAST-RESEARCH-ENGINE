"""Later immutable truth joins and arithmetic research contributions, never portfolio PnL."""

import math
from typing import TYPE_CHECKING

from afre.costs.artifacts import (
    CostAwareEvaluation,
    CostAwareSampleEvaluation,
    ResearchExposureChange,
    ResearchExposurePath,
    TotalCostEstimate,
)
from afre.costs.definitions import CostScenario
from afre.costs.schema import CostResultState
from afre.costs.sources import validate_uncertainty
from afre.costs.turnover import turnover
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition

if TYPE_CHECKING:
    from afre.costs.repository import CostResearchRepository


def sample_for(
    repo: "CostResearchRepository", total_id: str, cutoff_ns: int, available_ns: int
) -> CostAwareSampleEvaluation:
    total = repo.resolve(TotalCostEstimate, total_id)
    change = repo.resolve(ResearchExposureChange, total.change_id)
    scenario = repo.resolve(CostScenario, total.scenario_id)
    require(
        total.available_ns <= cutoff_ns <= available_ns,
        "costs actually available by later evaluation cutoff",
    )
    sample = repo.resolve(ResearchSample, change.sample_id)
    truth = repo.resolve(TargetVintage, sample.target_id) if sample.target_id else None
    gross = None
    truth_id = None
    if truth:
        require(
            truth.origin == change.origin and truth.definition == scenario.target,
            "gross exact immutable sample/target/horizon",
        )
        if target_known_by_cutoff(truth, cutoff_ns) and truth.value is not None:
            gross = change.exposure * truth.value
            truth_id = truth.fingerprint
    state = (
        CostResultState.AVAILABLE
        if gross is not None and total.amount is not None
        else CostResultState.EXCLUDED
    )
    validate_uncertainty(repo, scenario)
    uncertainty = tuple(
        i
        for i in scenario.uncertainty_ids
        if repo.resolve(ForecastUncertaintyDecomposition, i).sample_id == sample.fingerprint
    )
    require(
        all(
            repo.resolve(ForecastUncertaintyDecomposition, i).available_ns <= cutoff_ns
            for i in uncertainty
        ),
        "uncertainty actually available by cost evaluation",
    )
    return CostAwareSampleEvaluation(
        scenario.fingerprint,
        change.fingerprint,
        total_id,
        sample.fingerprint,
        change.origin,
        scenario.target.fingerprint,
        scenario.target.horizon.fingerprint,
        change.source_id,
        truth_id,
        gross,
        total.amount,
        gross - total.amount
        if state is CostResultState.AVAILABLE and gross is not None and total.amount is not None
        else None,
        state,
        "exact-gross-minus-declared-cost"
        if state is CostResultState.AVAILABLE
        else "truth-unavailable"
        if gross is None
        else total.reason,
        uncertainty,
        cutoff_ns,
        available_ns,
    )


def evaluation_for(
    repo: "CostResearchRepository",
    path_id: str,
    sample_ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
    seal: TestEvaluation | None,
) -> CostAwareEvaluation:
    path = repo.resolve(ResearchExposurePath, path_id)
    scenario = repo.resolve(CostScenario, path.scenario_id)
    rows = tuple(repo.resolve(CostAwareSampleEvaluation, i) for i in sorted(sample_ids))
    require(
        len(sample_ids) == len(set(sample_ids)) == len(scenario.sample_ids)
        and {r.sample_id for r in rows} == set(scenario.sample_ids)
        and {r.change_id for r in rows} == set(path.change_ids)
        and all(
            r.scenario_id == scenario.fingerprint
            and r.evaluation_cutoff_ns == cutoff_ns
            and r.available_ns == available_ns
            for r in rows
        ),
        "complete exact cost evaluation path/sample/cutoff",
    )
    partitions = {m.sample_id: m.partition for m in repo.fold_memberships(scenario.fold_id)}
    tests = tuple(r for r in rows if partitions[r.sample_id] is Partition.TEST)
    require(bool(tests) == (seal is not None), "explicit frozen cost TEST assessment")
    if seal:
        require(
            seal.fold_id == scenario.fold_id
            and seal.evaluated_ns == cutoff_ns
            and all(r.truth_id is None or r.sample_id in seal.sample_ids for r in tests),
            "cost TEST exact admitted fold/samples/cutoff",
        )
    valid = tuple(r for r in rows if r.state is CostResultState.AVAILABLE)
    gs = tuple(r.gross_contribution for r in valid if r.gross_contribution is not None)
    cs = tuple(r.total_cost for r in valid if r.total_cost is not None)
    ns = tuple(r.net_contribution for r in valid if r.net_contribution is not None)
    n = len(valid)
    gross, cost, net = (
        (math.fsum(gs), math.fsum(cs), math.fsum(ns)) if n else (None, None, None)
    )
    changes = tuple(repo.resolve(ResearchExposureChange, r.change_id) for r in rows)
    included_changes = tuple(repo.resolve(ResearchExposureChange, r.change_id) for r in valid)
    trades = turnover(included_changes)
    positive = tuple(
        r for r in valid if r.gross_contribution is not None and r.gross_contribution > 0
    )
    all_gross = tuple(r.gross_contribution for r in rows if r.gross_contribution is not None)
    enough = n >= scenario.minimum_count
    return CostAwareEvaluation(
        scenario.fingerprint,
        path_id,
        sample_ids,
        tuple(r.sample_id for r in valid),
        tuple(
            (r.sample_id, r.reason) for r in rows if r.state is not CostResultState.AVAILABLE
        ),
        len(rows),
        n,
        gross,
        cost,
        net,
        gross / n if gross is not None else None,
        cost / n if cost is not None else None,
        net / n if net is not None else None,
        math.fsum(all_gross) if all_gross else None,
        trades,
        turnover(changes),
        cost / trades if cost is not None and trades > 0 else None,
        sum(g > 0 for g in gs) / n if n else None,
        sum(v > 0 for v in ns) / n if n else None,
        cost / abs(gross) if gross is not None and gross != 0 and cost is not None else None,
        sum(r.net_contribution is not None and r.net_contribution > 0 for r in positive)
        / len(positive)
        if positive
        else None,
        CostResultState.AVAILABLE if enough else CostResultState.INSUFFICIENT_DATA,
        "matched-included-arithmetic-contributions" if enough else "declared-minimum-not-met",
        scenario.timing,
        seal.fingerprint if seal else None,
        cutoff_ns,
        available_ns,
    )
