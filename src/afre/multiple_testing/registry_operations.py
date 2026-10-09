"""Build full registry snapshots and replay their pinned historical membership."""

from collections import Counter
from typing import TYPE_CHECKING

from afre.multiple_testing.diagnostics import ResearchOverfittingDiagnostic
from afre.multiple_testing.families import HypothesisFamily
from afre.multiple_testing.hypotheses import HypothesisDefinition
from afre.multiple_testing.registry import TrialRegistrySnapshot
from afre.multiple_testing.schema import AdaptiveTrialStatus, TrialState
from afre.multiple_testing.selection_bias import SelectionEvent
from afre.multiple_testing.trials import ResearchTrial, TrialSpecification
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require

if TYPE_CHECKING:
    from afre.multiple_testing.repository import MultipleTestingRepository


def visible_ids(
    repo: "MultipleTestingRepository",
    cls: type[ResearchTrial]
    | type[TrialSpecification]
    | type[HypothesisFamily]
    | type[SelectionEvent],
    cutoff: int,
) -> tuple[str, ...]:
    b = repo.multiple_testing_bounds
    rows = repo._connection.execute(
        (
            "SELECT fingerprint FROM mt_records WHERE kind=? AND available_ns<=? "
            "ORDER BY fingerprint LIMIT ?"
        ),
        (cls.__name__, cutoff, b.trials + 1),
    ).fetchall()
    require(
        len(rows) <= (b.selection_events if cls is SelectionEvent else b.trials),
        "registry enumeration bound",
    )
    return tuple(r[0] for r in rows)


def snapshot_for(
    repo: "MultipleTestingRepository", cutoff_ns: int, available_ns: int
) -> TrialRegistrySnapshot:
    trials = visible_ids(repo, ResearchTrial, cutoff_ns)
    plans = visible_ids(repo, TrialSpecification, cutoff_ns)
    families = visible_ids(repo, HypothesisFamily, cutoff_ns)
    events = visible_ids(repo, SelectionEvent, cutoff_ns)
    native_seals = tuple(
        repo.resolve(TestEvaluation, r[0])
        for r in repo._connection.execute(
            "SELECT fingerprint FROM r_artifacts WHERE "
            "type_name='TestEvaluation' ORDER BY fingerprint LIMIT ?",
            (repo.multiple_testing_bounds.test_history + 1,),
        )
    )
    require(
        len(native_seals) <= repo.multiple_testing_bounds.test_history,
        "bounded total native TEST history",
    )
    seals = tuple(s.fingerprint for s in native_seals if s.evaluated_ns <= cutoff_ns)
    require(
        len(seals) <= repo.multiple_testing_bounds.test_history, "native TEST history bound"
    )
    return TrialRegistrySnapshot(
        trials,
        plans,
        families,
        events,
        seals,
        tuple((repo.resolve(ResearchTrial, i).completed_ns, i) for i in trials),
        cutoff_ns,
        available_ns,
    )


def validate_snapshot(
    repo: "MultipleTestingRepository", snapshot: TrialRegistrySnapshot
) -> None:
    require(
        all(
            repo.resolve(TrialSpecification, i).declared_ns <= snapshot.completion_cutoff_ns
            for i in snapshot.plan_ids
        ),
        "registry plan cutoff",
    )
    require(
        all(
            repo.resolve(HypothesisFamily, i).declared_ns <= snapshot.completion_cutoff_ns
            for i in snapshot.family_ids
        ),
        "registry family cutoff",
    )
    trials = tuple(repo.resolve(ResearchTrial, i) for i in snapshot.trial_ids)
    require(
        all(
            t.plan_id in snapshot.plan_ids
            and t.family_id in snapshot.family_ids
            and t.completed_ns <= snapshot.completion_cutoff_ns
            for t in trials
        )
        and snapshot.chronology
        == tuple(sorted((t.completed_ns, t.fingerprint) for t in trials)),
        "registry exact chronology/assignments/cutoff",
    )
    require(
        all(
            repo.resolve(SelectionEvent, i).available_ns <= snapshot.completion_cutoff_ns
            for i in snapshot.selection_event_ids
        ),
        "registry event cutoff",
    )
    require(
        all(
            repo.resolve(TestEvaluation, i).evaluated_ns <= snapshot.completion_cutoff_ns
            for i in snapshot.native_test_seal_ids
        ),
        "registry native seal cutoff",
    )


def overfitting_for(
    repo: "MultipleTestingRepository", registry_id: str, available_ns: int
) -> ResearchOverfittingDiagnostic:
    registry = repo.resolve(TrialRegistrySnapshot, registry_id)
    require(registry.available_ns <= available_ns, "diagnostic after registry availability")
    plans = tuple(repo.resolve(TrialSpecification, i) for i in registry.plan_ids)
    trials = tuple(repo.resolve(ResearchTrial, i) for i in registry.trial_ids)
    hypotheses = tuple(repo.resolve(HypothesisDefinition, p.hypothesis_id) for p in plans)
    opportunities = (
        ("hypotheses", len({h.fingerprint for h in hypotheses})),
        ("targets", len({h.target_id for h in hypotheses})),
        ("horizons", len({h.horizon_id for h in hypotheses})),
        ("metrics", len({h.metric for h in hypotheses})),
        ("native_sources", len({p.source_artifact_id for p in plans})),
        ("environments", len({p.environment_id for p in plans if p.environment_id})),
        ("cost_scenarios", len({p.cost_scenario_id for p in plans if p.cost_scenario_id})),
        ("choice_sets", len({p.choices for p in plans})),
    )
    counts: Counter[str] = Counter()
    for trial in trials:
        p = repo.resolve(TrialSpecification, trial.plan_id)
        h = repo.resolve(HypothesisDefinition, trial.hypothesis_id)
        # Each separately evaluated attempt counts, including unsuccessful ones.
        for label, identity in (
            ("target", h.target_id),
            ("dataset", p.dataset_id),
            ("horizon", h.horizon_id),
            ("fold", p.fold_id),
            ("metric", h.metric.value),
        ):
            counts[label + ":" + identity] += 1
        if trial.test_seal_ids:
            counts["TEST-fold:" + p.fold_id] += 1
    return ResearchOverfittingDiagnostic(
        registry_id,
        len(plans),
        sum(t.state is TrialState.COMPLETED for t in trials),
        sum(t.state is not TrialState.COMPLETED for t in trials),
        sum(p.adaptivity is AdaptiveTrialStatus.ADAPTIVE for p in plans),
        sum(p.adaptivity is AdaptiveTrialStatus.UNKNOWN for p in plans),
        opportunities,
        tuple(counts.items()),
        available_ns,
    )
