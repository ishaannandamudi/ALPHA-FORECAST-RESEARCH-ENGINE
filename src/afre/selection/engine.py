"""Frozen complete grid, TRAIN fits, VALIDATION decision, atomic publication."""

from collections.abc import Callable
from dataclasses import replace
from time import perf_counter

from afre.schema import Artifact, require
from afre.selection.accounting import complete_pool, exact_native_event, register_pool
from afre.selection.admission import admit
from afre.selection.comparisons import CandidateComparison
from afre.selection.decisions import ordering_for, winner_for
from afre.selection.definitions import CandidateFamilyPlan, SearchSpace, SelectionRequest
from afre.selection.enumeration import enumerate_candidates
from afre.selection.fitting import fit_candidate
from afre.selection.guards import read_role
from afre.selection.lineage import SelectionAudit
from afre.selection.registry import CandidateRegistryEntry, CandidateRegistrySnapshot
from afre.selection.repository import SelectionRepository
from afre.selection.results import SelectionResult
from afre.selection.schema import CandidateStatus, SelectionReadRole
from afre.selection.scoring import score_candidate
from afre.selection.snapshots import frozen_copy, publish_stage
from afre.serialization import canonical_json


class SelectionEngine:
    def __init__(self, repository: SelectionRepository) -> None:
        self.repository = repository
        self.last_timings: dict[str, float] = {}

    def select(
        self,
        space: SearchSpace,
        cutoff_ns: int,
        available_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> tuple[SelectionResult, CandidateRegistrySnapshot]:
        require(space.declared_ns <= cutoff_ns <= available_ns, "selection request clocks")
        start = perf_counter()
        stage = frozen_copy(self.repository, snapshot_hook)
        self.last_timings = {"frozen_snapshot_seconds": perf_counter() - start}
        try:
            with read_role(stage, SelectionReadRole.PLANNING, space):
                start = perf_counter()
                usage = admit(stage, space)
                candidates = enumerate_candidates(space)
                request = SelectionRequest(space.fingerprint, cutoff_ns, available_ns)
                family_plan = CandidateFamilyPlan(
                    request.fingerprint,
                    space.fingerprint,
                    tuple(c.fingerprint for c in candidates),
                    space.declared_ns,
                )
                with stage.transaction():
                    for value in (
                        space.budget,
                        *space.dimensions,
                        *space.recipes,
                        space,
                        *candidates,
                        request,
                        family_plan,
                    ):
                        stage.put(value)
                self.last_timings["admission_enumeration_seconds"] = perf_counter() - start
            with read_role(stage, SelectionReadRole.FIT, space):
                start = perf_counter()
                fits = tuple(fit_candidate(stage, space, c, cutoff_ns) for c in candidates)
                self._publish(stage, fits)
                self.last_timings["fit_orchestration_seconds"] = perf_counter() - start
                start = perf_counter()
                family, plans = register_pool(stage, space, candidates, fits, request)
                self.last_timings["AFRE19_registration_seconds"] = perf_counter() - start
            with read_role(stage, SelectionReadRole.VALIDATION, space):
                start = perf_counter()
                trials = complete_pool(stage, family, plans, fits, cutoff_ns, available_ns)
                self.last_timings["AFRE19_completion_seconds"] = perf_counter() - start
                start = perf_counter()
                results = tuple(
                    score_candidate(stage, space, f, t.fingerprint, cutoff_ns, available_ns)
                    for f, t in zip(fits, trials, strict=True)
                )
                self._publish(stage, results)
                self.last_timings["validation_scoring_seconds"] = perf_counter() - start
                start = perf_counter()
                ordering = ordering_for(space, results)
                winner, status = winner_for(space, results)
                model = next((f.model_id for f in fits if f.candidate_id == winner), None)
                event = exact_native_event(
                    stage, space, results, ordering, winner, cutoff_ns, available_ns
                )
                if event is not None:
                    self._publish(stage, (event,))
                payload = sum(len(canonical_json(r).encode()) for r in (*fits, *results))
                require(
                    payload + usage.payload_bytes <= space.budget.max_payload_bytes,
                    "selection result payload budget",
                )
                usage = replace(
                    usage,
                    fit_operations_attempted=sum(f.fit_operations_attempted for f in fits),
                    fitted_candidates=sum(f.status is CandidateStatus.VALID for f in fits),
                    validation_pairs=sum(len(r.pairs) for r in results),
                    payload_bytes=payload + usage.payload_bytes,
                )
                result = SelectionResult(
                    request.fingerprint,
                    space.fingerprint,
                    family_plan.fingerprint,
                    tuple(c.fingerprint for c in candidates),
                    tuple(r.fingerprint for r in results),
                    ordering,
                    winner,
                    model,
                    space.criterion,
                    status,
                    cutoff_ns,
                    available_ns,
                    family.fingerprint,
                    event.fingerprint if event else None,
                    "EXACT_NATIVE_EVENT"
                    if event
                    else "NO_VALID_CANDIDATE"
                    if winner is None
                    else "INCOMPATIBLE_NATIVE_MEDIAN_PROTOCOL",
                    usage,
                )
                self._publish(stage, (result,))
                self.last_timings["decision_seconds"] = perf_counter() - start
                start = perf_counter()
                registry = CandidateRegistrySnapshot(
                    space.fingerprint,
                    result.fingerprint,
                    tuple(
                        CandidateRegistryEntry(
                            r.candidate_id,
                            r.fit_id,
                            next(f.model_id for f in fits if f.fingerprint == r.fit_id),
                            r.fingerprint,
                            r.trial_id,
                            r.status,
                        )
                        for r in results
                    ),
                    available_ns,
                )
                self._publish(stage, (registry,))
                self.last_timings["registry_snapshot_seconds"] = perf_counter() - start
            start = perf_counter()
            publish_stage(self.repository, stage)
            self.last_timings["atomic_persistence_seconds"] = perf_counter() - start
            return result, registry
        finally:
            stage.close()

    @staticmethod
    def _publish(repo: SelectionRepository, values: tuple[Artifact, ...]) -> None:
        with repo.transaction(), repo.validation_cache():
            for value in values:
                repo.put(value)

    def audit(self, root_id: str) -> SelectionAudit:
        from afre.selection.lineage import audit_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = audit_for(self.repository, root_id)
        self._publish(self.repository, (result,))
        return result

    def compare(
        self, left_validation_id: str, right_validation_id: str, minimum_support: int = 2
    ) -> CandidateComparison:
        from afre.selection.comparisons import comparison_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = comparison_for(
                self.repository, left_validation_id, right_validation_id, minimum_support
            )
        self._publish(self.repository, (result,))
        return result
