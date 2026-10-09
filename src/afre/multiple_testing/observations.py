"""Later exact immutable truth joins and explicit matched-pair intersections."""

from typing import TYPE_CHECKING

from afre.costs.artifacts import CostAwareEvaluation, CostAwareSampleEvaluation
from afre.invariance.artifacts import EnvironmentMembership
from afre.multiple_testing.families import HypothesisFamily
from afre.multiple_testing.hypotheses import HypothesisDefinition
from afre.multiple_testing.schema import RawTestMethod, ResearchMetric, TrialState
from afre.multiple_testing.sources import source_grid
from afre.multiple_testing.trials import ResearchTrial, TrialObservation, TrialSpecification
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.multiple_testing.repository import MultipleTestingRepository


def metric_value(metric: ResearchMetric, prediction: float, truth: float) -> float:
    if metric is ResearchMetric.TARGET_RETURN:
        return truth
    if metric is ResearchMetric.FORECAST_ERROR:
        return prediction - truth
    if metric is ResearchMetric.ABSOLUTE_ERROR:
        return abs(prediction - truth)
    if metric is ResearchMetric.SQUARED_ERROR:
        return (prediction - truth) ** 2
    require(
        metric is ResearchMetric.RESIDUAL_VALUE,
        "net contribution requires native cost evidence",
    )
    return prediction


def trial_for(
    repo: "MultipleTestingRepository",
    plan_id: str,
    family_id: str,
    state: TrialState,
    reason: str,
    native_result_ids: tuple[str, ...],
    test_seal_ids: tuple[str, ...],
    cutoff_ns: int,
    completed_ns: int,
    pending_seal: TestEvaluation | None = None,
) -> ResearchTrial:
    plan = repo.resolve(TrialSpecification, plan_id)
    family = repo.resolve(HypothesisFamily, family_id)
    h = repo.resolve(HypothesisDefinition, plan.hypothesis_id)
    require(
        plan_id in family.plan_ids and family.declared_ns <= cutoff_ns <= completed_ns,
        "trial belongs to declared family/chronology",
    )
    left = {s.sample_id: s for s in source_grid(repo, plan)}
    right = {s.sample_id: s for s in source_grid(repo, plan, True)}
    require(
        (bool(right) == (h.method is RawTestMethod.EXACT_PAIRED_SIGN))
        or h.method in (RawTestMethod.NORMAL_MEAN, RawTestMethod.CORRELATION),
        "declared exact pairing/test method",
    )
    members = {
        m.sample_id: m
        for i in plan.membership_ids
        if isinstance((m := repo.resolve(EnvironmentMembership, i)), EnvironmentMembership)
    }
    require(
        all(m.available_ns <= cutoff_ns for m in members.values()),
        "environment evidence actually available at evaluation cutoff",
    )
    parts = {m.sample_id: m.partition for m in repo.fold_memberships(plan.fold_id)}
    tests = set(s for s in (*left, *right) if parts[s] is Partition.TEST)
    seals = tuple(
        pending_seal
        if pending_seal is not None and i == pending_seal.fingerprint
        else repo.resolve(TestEvaluation, i)
        for i in test_seal_ids
    )
    require(not seals or bool(tests), "no TEST seal for validation-only trial")
    require(
        state is not TrialState.COMPLETED or bool(seals) == bool(tests),
        "completed TEST trial requires existing exact native seal",
    )
    require(
        all(
            s.fold_id == plan.fold_id
            and s.evaluated_ns <= cutoff_ns
            and tests <= set(s.sample_ids)
            for s in seals
        ),
        "TEST seal exact fold/sample/cutoff",
    )
    costs: dict[str, CostAwareSampleEvaluation] = {}
    for identity in native_result_ids:
        evaluation = repo.resolve(CostAwareEvaluation, identity)
        require(
            evaluation.scenario_id == plan.cost_scenario_id
            and evaluation.evaluation_cutoff_ns <= cutoff_ns
            and evaluation.available_ns <= cutoff_ns
            and (
                evaluation.test_evaluation_id is None
                or evaluation.test_evaluation_id in test_seal_ids
            ),
            "native cost trial result exact scenario/cutoff/TEST",
        )
        for row_id in evaluation.sample_evaluation_ids:
            cost_row = repo.resolve(CostAwareSampleEvaluation, row_id)
            require(cost_row.sample_id not in costs, "one cost result per trial sample")
            costs[cost_row.sample_id] = cost_row
    require(
        h.metric is ResearchMetric.NET_CONTRIBUTION or not native_result_ids,
        "only native cost metrics consume cost result evidence",
    )
    require(
        state is not TrialState.COMPLETED
        or h.metric is not ResearchMetric.NET_CONTRIBUTION
        or len(native_result_ids) == 1,
        "net trial requires one exact supplied cost evaluation",
    )
    observations = []
    excluded: list[tuple[str, str]] = []
    if state is TrialState.COMPLETED:
        for sample_id in sorted(set(left) | set(right)):
            if sample_id not in left or right and sample_id not in right:
                excluded.append((sample_id, "outside-exact-left-right-sample-intersection"))
                continue
            if members and members[sample_id].weight <= 0:
                excluded.append((sample_id, "outside-declared-PIT-environment"))
                continue
            source = left[sample_id]
            sample = repo.resolve(ResearchSample, sample_id)
            truth = repo.resolve(TargetVintage, sample.target_id) if sample.target_id else None
            if (
                truth is None
                or truth.value is None
                or not target_known_by_cutoff(truth, cutoff_ns)
            ):
                excluded.append((sample_id, "exact-immutable-truth-unavailable-at-cutoff"))
                continue
            require(
                truth.origin == source.origin and truth.definition.fingerprint == h.target_id,
                "trial exact source/truth target and origin",
            )
            native_id = None
            if h.metric is ResearchMetric.NET_CONTRIBUTION:
                row = costs.get(sample_id)
                if row is None or row.net_contribution is None:
                    excluded.append((sample_id, "native-net-contribution-unavailable"))
                    continue
                require(
                    row.truth_id == truth.fingerprint
                    and row.source_id == source.identity
                    and row.target_id == h.target_id
                    and row.horizon_id == h.horizon_id,
                    "net trial exact immutable sample/truth/source intersection",
                )
                value, native_id = row.net_contribution, row.fingerprint
            else:
                value = metric_value(h.metric, source.prediction, truth.value)
                if right:
                    other = right[sample_id]
                    require(
                        other.origin == source.origin and other.unit == source.unit,
                        "paired trial exact origin/truth/units",
                    )
                    value -= metric_value(h.metric, other.prediction, truth.value)
            observations.append(
                TrialObservation(
                    sample_id,
                    truth.fingerprint,
                    source.identity,
                    right[sample_id].identity if right else None,
                    value,
                    source.unit,
                    native_id,
                )
            )
    return ResearchTrial(
        plan_id,
        family_id,
        h.fingerprint,
        state,
        reason,
        tuple(observations),
        tuple(excluded),
        native_result_ids,
        test_seal_ids,
        cutoff_ns,
        completed_ns,
    )
