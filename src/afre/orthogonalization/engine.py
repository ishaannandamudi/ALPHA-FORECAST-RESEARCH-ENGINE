"""Atomic publication and frozen snapshots; supplied transforms, no selection or pruning."""

from collections.abc import Callable

from afre.cross_sectional.artifacts import CrossSectionRanking
from afre.cross_sectional.definitions import CrossSectionSpec
from afre.orthogonalization.artifacts import (
    AlignedSignalRow,
    OrthogonalizationAudit,
    OrthogonalSignalValue,
    ProjectionArtifact,
    RedundancyMatrix,
)
from afre.orthogonalization.definitions import OrthogonalizationSpec, SignalReference
from afre.orthogonalization.evaluation_artifacts import (
    PartialCorrelation,
    PredictiveModelPair,
    RedundancyEvaluation,
    RedundancyStability,
)
from afre.orthogonalization.repository import OrthogonalizationRepository
from afre.orthogonalization.signals import GenericSignalSource, SignalObservation
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require


class OrthogonalizationEngine:
    def __init__(self, repository: OrthogonalizationRepository) -> None:
        self.repository = repository

    def _publish(self, values: tuple[Artifact, ...]) -> None:
        with self.repository.transaction(), self.repository.validation_cache():
            for v in values:
                self.repository.put(v)

    def register(self, reference: SignalReference) -> SignalReference:
        self._publish((*((reference.target,) if reference.target else ()), reference))
        return reference

    def publish_generic(self, source: GenericSignalSource) -> GenericSignalSource:
        self.register(source.reference)
        self._publish(
            (
                source.source,
                *(
                    (source.clocks.historical_delivery,)
                    if source.clocks.historical_delivery
                    else ()
                ),
                source,
            )
        )
        return source

    def bind(
        self,
        reference: SignalReference,
        source_id: str,
        sample_id: str,
        approved_attestors: tuple[str, ...] = (),
    ) -> SignalObservation:
        from afre.orthogonalization.sources import observation_for

        self.register(reference)
        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            result = observation_for(
                self.repository, reference, source_id, sample_id, approved_attestors
            )
        self._publish((result,))
        return result

    def align(self, spec: OrthogonalizationSpec, ids: tuple[str, ...]) -> AlignedSignalRow:
        from afre.orthogonalization.alignment import row_for

        self._publish((spec.target, spec))
        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            result = row_for(self.repository, spec, ids)
        self._publish((result,))
        return result

    def matrix(
        self, spec_id: str, row_ids: tuple[str, ...], available_ns: int
    ) -> RedundancyMatrix:
        from afre.orthogonalization.correlation import matrix_for

        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            result = matrix_for(self.repository, spec_id, row_ids, available_ns)
        self._publish((result,))
        return result

    def fit(
        self,
        spec: OrthogonalizationSpec,
        row_ids: tuple[str, ...],
        computed_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> ProjectionArtifact:
        from afre.orthogonalization.projection import projection_for

        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            self.repository.get_any(spec.fingerprint)
            if snapshot_hook:
                snapshot_hook()
            from afre.orthogonalization.correlation import matrix_for

            matrix = matrix_for(self.repository, spec.fingerprint, row_ids, computed_ns)
            result = projection_for(
                self.repository, spec, row_ids, matrix.fingerprint, computed_ns, matrix
            )
        self._publish((matrix, result))
        return result

    def residual(
        self,
        projection_id: str,
        row_id: str,
        computed_ns: int,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> OrthogonalSignalValue:
        from afre.orthogonalization.residualization import residual_for

        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            self.repository.get_any(projection_id)
            if snapshot_hook:
                snapshot_hook()
            result = residual_for(self.repository, projection_id, row_id, computed_ns)
        self._publish((result,))
        return result

    def fit_target_models(
        self, projection_id: str, computed_ns: int, use_residual: bool = True
    ) -> PredictiveModelPair:
        from afre.orthogonalization.incremental import target_models_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = target_models_for(
                self.repository, projection_id, computed_ns, use_residual
            )
        self._publish((result,))
        return result

    def evaluate(
        self,
        ids: tuple[str, ...],
        cutoff_ns: int,
        available_ns: int,
        predictive_pair_id: str | None = None,
        target_diagnostics: bool = False,
        test_identity: str | None = None,
        snapshot_hook: Callable[[], None] | None = None,
    ) -> RedundancyEvaluation:
        from afre.orthogonalization.evaluation import evaluation_for
        from afre.statistical_models.evaluation import test_record

        require(bool(ids), "evaluation requires residuals")
        with self.repository.read_snapshot(), self.repository.validation_cache():
            first = self.repository.resolve(OrthogonalSignalValue, ids[0])
            row = self.repository.resolve(AlignedSignalRow, first.row_id)
            spec = self.repository.resolve(OrthogonalizationSpec, row.spec_id)
            if snapshot_hook:
                snapshot_hook()
            seal = None
            if row.partition is Partition.TEST:
                require(test_identity is not None, "explicit orthogonal TEST identity")
                seal = test_record(
                    self.repository,
                    spec.fold_id,
                    test_identity or "",
                    "orthogonal-frozen-matched-assessment",
                    cutoff_ns,
                )
            result = evaluation_for(
                self.repository,
                ids,
                cutoff_ns,
                available_ns,
                predictive_pair_id,
                target_diagnostics,
                seal,
            )
        self._publish((*((seal,) if seal else ()), result))
        return result

    def partial(
        self, left: tuple[str, ...], right: tuple[str, ...], available_ns: int
    ) -> PartialCorrelation:
        from afre.orthogonalization.partial import partial_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = partial_for(self.repository, left, right, available_ns)
        self._publish((result,))
        return result

    def stability(self, ids: tuple[str, ...], available_ns: int) -> RedundancyStability:
        from afre.orthogonalization.diagnostics import stability_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = stability_for(self.repository, ids, available_ns)
        self._publish((result,))
        return result

    def audit_lineage(self, root_id: str) -> OrthogonalizationAudit:
        from afre.orthogonalization.lineage import audit_for

        with self.repository.read_snapshot(), self.repository.validation_cache():
            result = audit_for(self.repository, root_id)
        self._publish((result,))
        return result

    def fit_candidates(
        self,
        requests: tuple[tuple[OrthogonalizationSpec, tuple[str, ...]], ...],
        computed_ns: int,
    ) -> tuple[ProjectionArtifact, ...]:
        require(
            0 < len(requests) <= self.repository.orthogonalization_bounds.candidates
            and len({s.candidate for s, _ in requests}) == len(requests),
            "supplied multi-candidate bound/duplicates",
        )
        return tuple(
            self.fit(s, ids, computed_ns)
            for s, ids in sorted(requests, key=lambda r: r[0].fingerprint)
        )

    def rank(
        self,
        template: "CrossSectionSpec",
        ids: tuple[str, ...],
        groups: tuple[tuple[str, str], ...] = (),
    ) -> "CrossSectionRanking":
        from afre.cross_sectional.engine import CrossSectionEngine
        from afre.orthogonalization.alignment import validate_cross_sectional_grid
        from afre.orthogonalization.cross_sectional import ranking_spec, residual_signal

        require(
            0 < len(ids) <= self.repository.orthogonalization_bounds.rows
            and len(set(ids)) == len(ids),
            "orthogonal rank bounds/duplicates",
        )
        with (
            self.repository.feature_only(),
            self.repository.read_snapshot(),
            self.repository.validation_cache(),
        ):
            values = tuple(
                self.repository.resolve(OrthogonalSignalValue, i) for i in sorted(ids)
            )
            require(
                len({v.projection_id for v in values}) == 1, "ranking exact frozen projection"
            )
            rows = tuple(self.repository.resolve(AlignedSignalRow, v.row_id) for v in values)
            validate_cross_sectional_grid(self.repository, rows)
            spec = ranking_spec(self.repository, template, values[0])
            require(
                all(ranking_spec(self.repository, template, v) == spec for v in values),
                "ranking exact common origin",
            )
            signals = tuple(residual_signal(self.repository, v) for v in values)
        e = CrossSectionEngine(self.repository)
        for signal in signals:
            e.publish_external(signal)
        return e.build_ranking(
            spec, tuple((s.security.fingerprint, s.fingerprint) for s in signals), groups
        )
