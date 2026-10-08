"""Atomic hypothetical research publication on frozen snapshots; no execution or fit APIs."""

from collections.abc import Callable

from afre.costs.artifacts import (
    BreakEvenCostDiagnostic,
    CostAwareComparison,
    CostAwareEvaluation,
    CostCohortEvaluation,
    CostComponentEstimate,
    CostResearchAudit,
    CostSensitivityCurve,
    ResearchExposurePath,
    TotalCostEstimate,
)
from afre.costs.cost_inputs import CostInputReference
from afre.costs.definitions import CostScenario, CostSensitivitySpec
from afre.costs.repository import CostResearchRepository
from afre.costs.schema import CostTiming
from afre.forecast import ForecastOrigin
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require


class CostResearchEngine:
    def __init__(self, repository: CostResearchRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for value in values:
                self.repository.put(value)

    def publish_input(self, value: CostInputReference) -> CostInputReference:
        proof = value.clocks.historical_delivery
        self._publish((value.source, *((proof,) if proof else ()), value))
        return value

    def declare(self, scenario: CostScenario) -> CostScenario:
        self._publish((scenario.target, scenario.exposure_rule, *scenario.components, scenario))
        return scenario

    def register_sensitivity(self, spec: CostSensitivitySpec) -> CostSensitivitySpec:
        self._publish((spec,))
        return spec

    def estimate(
        self,
        scenario_id: str,
        constructed_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> tuple[ResearchExposurePath, tuple[TotalCostEstimate, ...]]:
        from afre.costs.components import component_for
        from afre.costs.exposures import path_for
        from afre.costs.totals import total_from

        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            scenario = self.repository.resolve(CostScenario, scenario_id)
            if snapshot_hook:
                snapshot_hook()
            changes, path = path_for(self.repository, scenario_id, constructed_ns)
            components: list[CostComponentEstimate] = []
            totals = []
            for c in changes:
                selected = tuple(
                    component_for(self.repository, c, s.fingerprint)
                    for s in scenario.components
                )
                components.extend(selected)
                totals.append(total_from(scenario, c, selected))
        # Publication replay verifies these exact IDs in a writer transaction.
        with self.repository.feature_only():
            self._publish((*changes, path, *components, *totals))
        return path, tuple(totals)

    def metadata(self, total_id: str, origin: ForecastOrigin) -> TotalCostEstimate:
        from afre.costs.artifacts import ResearchExposureChange

        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            total = self.repository.resolve(TotalCostEstimate, total_id)
            change = self.repository.resolve(ResearchExposureChange, total.change_id)
            require(
                change.origin == origin
                and total.timing is CostTiming.HISTORICAL_CAUSAL
                and total.available_ns <= origin.availability_cutoff_ns,
                "cost metadata not actually available at exact causal origin",
            )
            return total

    def evaluate(
        self,
        path_id: str,
        total_ids: tuple[str, ...],
        cutoff_ns: int,
        available_ns: int,
        test_identity: str | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> CostAwareEvaluation:
        from afre.costs.evaluation import evaluation_for, sample_for
        from afre.statistical_models.evaluation import test_record

        with self.repository.read_snapshot(), self.repository.validation_cache():
            path = self.repository.resolve(ResearchExposurePath, path_id)
            scenario = self.repository.resolve(CostScenario, path.scenario_id)
            totals = tuple(self.repository.resolve(TotalCostEstimate, i) for i in total_ids)
            require(
                len(total_ids) == len(set(total_ids)) == len(path.change_ids)
                and {t.change_id for t in totals} == set(path.change_ids),
                "exact complete path total-cost set",
            )
            if snapshot_hook:
                snapshot_hook()
            rows = tuple(
                sample_for(self.repository, i, cutoff_ns, available_ns)
                for i in sorted(total_ids)
            )
            seal = None
            if any(
                m.partition is Partition.TEST and m.sample_id in scenario.sample_ids
                for m in self.repository.fold_memberships(scenario.fold_id)
            ):
                require(test_identity is not None, "explicit cost TEST assessment identity")
                seal = test_record(
                    self.repository,
                    scenario.fold_id,
                    test_identity or "",
                    "cost-research-frozen-scenario-assessment",
                    cutoff_ns,
                )
        with self.repository.transaction(), self.repository.validation_cache():
            if seal:
                self.repository.put(seal)
            for row in rows:
                self.repository.put(row)
            value = evaluation_for(
                self.repository,
                path_id,
                tuple(r.fingerprint for r in rows),
                cutoff_ns,
                available_ns,
                seal,
            )
            self.repository.put(value)
        return value

    def _diagnostic(self, compute: Callable[[], Artifact]) -> Artifact:
        with self.repository.read_snapshot(), self.repository.validation_cache():
            value = compute()
        self._publish((value,))
        return value

    def breakeven(
        self, evaluation_id: str, available_ns: int, component_id: str | None = None
    ) -> BreakEvenCostDiagnostic:
        from afre.costs.breakeven import breakeven_for

        value = self._diagnostic(
            lambda: breakeven_for(self.repository, evaluation_id, component_id, available_ns)
        )
        assert isinstance(value, BreakEvenCostDiagnostic)
        return value

    def sensitivity(
        self, evaluation_id: str, spec_id: str, available_ns: int
    ) -> CostSensitivityCurve:
        from afre.costs.sensitivity import sensitivity_for

        value = self._diagnostic(
            lambda: sensitivity_for(self.repository, evaluation_id, spec_id, available_ns)
        )
        assert isinstance(value, CostSensitivityCurve)
        return value

    def compare(self, left_id: str, right_id: str, available_ns: int) -> CostAwareComparison:
        from afre.costs.comparisons import comparison_for

        value = self._diagnostic(
            lambda: comparison_for(self.repository, left_id, right_id, available_ns)
        )
        assert isinstance(value, CostAwareComparison)
        return value

    def cohort(
        self,
        evaluation_id: str,
        environment_id: str,
        membership_ids: tuple[str, ...],
        available_ns: int,
    ) -> CostCohortEvaluation:
        from afre.costs.cohorts import cohort_for

        value = self._diagnostic(
            lambda: cohort_for(
                self.repository, evaluation_id, environment_id, membership_ids, available_ns
            )
        )
        assert isinstance(value, CostCohortEvaluation)
        return value

    def audit(self, root_id: str) -> CostResearchAudit:
        from afre.costs.lineage import audit_for

        value = self._diagnostic(lambda: audit_for(self.repository, root_id))
        assert isinstance(value, CostResearchAudit)
        return value

    def cohorts(
        self,
        evaluation_id: str,
        requests: tuple[tuple[str, tuple[str, ...]], ...],
        available_ns: int,
    ) -> tuple[CostCohortEvaluation, ...]:
        from afre.costs.cohorts import cohort_for

        require(
            1 <= len(requests) <= self.repository.cost_research_bounds.environments
            and len({i for i, _ in requests}) == len(requests),
            "cost cohort request bounds/duplicates",
        )
        with self.repository.read_snapshot(), self.repository.validation_cache():
            values = tuple(
                cohort_for(self.repository, evaluation_id, i, members, available_ns)
                for i, members in sorted(requests)
            )
        self._publish(values)
        return values
