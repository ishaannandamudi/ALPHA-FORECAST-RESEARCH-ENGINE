"""Feature-store API; all joins share the same snapshot-scoped as-of selection."""

from afre.datasets import DatasetManifest, ForecastFeatureRow
from afre.feature_store.computation import IMPLEMENTATION_VERSION, transform
from afre.feature_store.dag import FeatureComputationSpec, MissingInputPolicy, WindowBasis
from afre.feature_store.materialization import (
    FeatureAudit,
    FeatureComputationReceipt,
    FeatureMaterialization,
    PointInTimeJoinResult,
)
from afre.feature_store.models import (
    AvailabilityEvidence,
    FeatureSetManifest,
    FeatureVintage,
    RegisteredFeatureDefinition,
    SourceReference,
)
from afre.feature_store.normalization import NormalizationState
from afre.feature_store.queries import (
    feature_history,
    resolve_entity,
    select_as_of,
    window_history,
)
from afre.feature_store.registry import FeatureRegistry
from afre.feature_store.repository import FeatureStoreRepository
from afre.feature_store.schema import QueryPolicy
from afre.features import DataQuality, FeatureValue, MissingState
from afre.forecast import ForecastOrigin
from afre.hashing import bytes_digest
from afre.ids import InstrumentId
from afre.lineage import FeatureDependency, FeatureLineage, Parameter, ProvenanceRef
from afre.schema import require
from afre.serialization import canonical_json


class FeatureStore:
    def __init__(
        self, repository: FeatureStoreRepository, policy: QueryPolicy | None = None
    ) -> None:
        self.repository = repository
        self.registry = FeatureRegistry(repository)
        self.policy = policy or QueryPolicy()

    def append_vintage(self, vintage: FeatureVintage) -> str:
        require(
            vintage.computation_spec_id is None, "derived vintages require trusted computation"
        )
        self._authorize_delivery(vintage)
        return self.repository.put(vintage)

    def _authorize_delivery(self, vintage: FeatureVintage) -> None:
        delivery = vintage.clocks.historical_delivery
        if delivery is not None:
            require(
                delivery.attestor in self.policy.approved_delivery_attestors,
                "historical delivery attestor is not locally approved",
            )

    def feature_as_of(
        self, feature: RegisteredFeatureDefinition, origin: ForecastOrigin
    ) -> FeatureAudit:
        with self.repository.read_snapshot():
            audit = select_as_of(self.repository, feature, origin, self.policy)
        self._byte_bound((audit,))
        return audit

    def features_as_of(
        self, features: FeatureSetManifest, origin: ForecastOrigin
    ) -> tuple[FeatureAudit, ...]:
        require(
            len(features.definitions) <= self.repository.bounds.features,
            "feature query bound exceeded",
        )
        with self.repository.read_snapshot():
            audits = tuple(
                select_as_of(self.repository, feature, origin, self.policy)
                for feature in features.definitions
            )
        self._byte_bound(audits)
        return audits

    def _byte_bound(self, artifacts: tuple[object, ...]) -> None:
        from afre.schema import ensure_artifact

        require(
            sum(len(canonical_json(ensure_artifact(value)).encode()) for value in artifacts)
            <= self.repository.bounds.serialized_bytes,
            "query serialized byte bound exceeded",
        )

    def _projection(self, audit: FeatureAudit, active: tuple[str, ...] = ()) -> FeatureValue:
        if audit.selected is not None:
            return audit.selected.to_feature_value(
                audit.origin.instrument, audit.state, audit.query_policy.fingerprint
            )
        identity = audit.feature.definition.fingerprint
        require(
            identity not in active and len(active) < self.repository.bounds.lineage_depth,
            "missing projection dependency cycle/depth",
        )
        refs: list[FeatureDependency] = []
        for dependency in audit.feature.definition.dependency_ids:
            row = self.repository._connection.execute(
                "SELECT fingerprint FROM fs_definitions WHERE foundation_id = ?", (dependency,)
            ).fetchone()
            require(row is not None, "missing projection dependency is unregistered")
            assert row is not None
            definition = self.registry.get(row[0])
            child = self._projection(
                FeatureAudit(
                    definition,
                    audit.origin,
                    MissingState.MISSING,
                    None,
                    None,
                    "missing dependency at cutoff",
                    self.policy,
                ),
                (*active, identity),
            )
            refs.append(FeatureDependency(dependency, child.fingerprint, child.available_ns))
        origin = audit.origin
        source = ProvenanceRef(
            "AFRE-absence-audit",
            "absence-at-cutoff",
            "1.0",
            bytes_digest((identity + origin.fingerprint).encode()),
        )
        lineage = FeatureLineage(
            (source,),
            tuple(refs),
            audit.feature.definition.transformation_version,
            (
                Parameter("query_policy", self.policy.fingerprint),
                Parameter("freshness", audit.feature.freshness.fingerprint),
            ),
            audit.feature.build_context,
            "afre-feature-store-v1",
            origin.availability_cutoff_ns if refs else None,
        )
        return FeatureValue(
            audit.feature.definition,
            origin.instrument,
            origin.timestamp_ns,
            origin.availability_cutoff_ns,
            origin.availability_cutoff_ns,
            None,
            audit.state,
            "AFRE-absence-audit",
            "1.0",
            DataQuality.UNVERIFIED,
            lineage,
        )

    def point_in_time_join(
        self,
        origins: tuple[ForecastOrigin, ...],
        dataset: DatasetManifest,
        features: FeatureSetManifest,
    ) -> tuple[PointInTimeJoinResult, ...]:
        bounds = self.repository.bounds
        require(0 < len(origins) <= bounds.origins, "origin query bound exceeded")
        require(
            len({item.instrument for item in origins}) <= bounds.instruments,
            "instrument query bound exceeded",
        )
        require(
            len(features.definitions) <= bounds.features
            and len(origins) * len(features.definitions) <= bounds.cells,
            "feature/cell query bound exceeded",
        )
        require(
            {item.definition.fingerprint for item in features.definitions}
            == {item.fingerprint for item in dataset.feature_set.definitions},
            "join/dataset feature mismatch",
        )
        for feature in features.definitions:
            require(
                feature.calendar_id == dataset.calendar_id
                and feature.adjustment == dataset.adjustment,
                "join calendar/adjustment mismatch",
            )
            require(
                set(feature.source_dataset_ids).issubset(
                    {*dataset.source_dataset_ids, *self.policy.compatible_dataset_ids}
                ),
                "cross-dataset join requires explicit compatibility policy",
            )
        results: list[PointInTimeJoinResult] = []
        with self.repository.read_snapshot():
            for origin in origins:
                audits = tuple(
                    select_as_of(self.repository, feature, origin, self.policy)
                    for feature in features.definitions
                )
                row = ForecastFeatureRow(
                    origin, dataset, tuple(self._projection(audit) for audit in audits)
                )
                results.append(PointInTimeJoinResult(row, audits))
        answer = tuple(results)
        self._byte_bound(answer)
        return answer

    def materialize(
        self,
        origins: tuple[ForecastOrigin, ...],
        dataset: DatasetManifest,
        features: FeatureSetManifest,
        created_ns: int,
    ) -> FeatureMaterialization:
        materialization = FeatureMaterialization(
            self.point_in_time_join(origins, dataset, features),
            created_ns,
            "afre-feature-store-v1",
        )
        with self.repository.transaction():
            self.repository.put(materialization)
        return materialization

    def feature_history(
        self, feature: RegisteredFeatureDefinition, entity: InstrumentId, known_as_of_ns: int
    ) -> tuple[FeatureVintage, ...]:
        with self.repository.read_snapshot():
            return feature_history(self.repository, feature, entity, known_as_of_ns)

    def compute(
        self, spec: FeatureComputationSpec, origin: ForecastOrigin, clocks: AvailabilityEvidence
    ) -> tuple[FeatureVintage, FeatureComputationReceipt]:
        require(
            spec.implementation_version == IMPLEMENTATION_VERSION,
            "unrecognized trusted transformation implementation version",
        )
        require(spec.output.build_context == origin.build_context, "computation build mismatch")
        # One writer snapshot pins inputs, normalization state, output and receipt.
        with self.repository.transaction():
            self.repository.put(spec)
            inputs: list[FeatureVintage] = []
            for feature in spec.inputs:
                audit = select_as_of(self.repository, feature, origin, self.policy)
                if spec.window_basis is WindowBasis.LATEST_VALUES:
                    if audit.selected is not None and audit.state is MissingState.PRESENT:
                        inputs.append(audit.selected)
                else:
                    entity, _ = resolve_entity(self.repository, feature, origin)
                    if entity is not None:
                        inputs.extend(
                            window_history(
                                self.repository,
                                feature,
                                entity,
                                origin,
                                spec.output.definition.lookback_ns,
                                spec.observation_count,
                                self.policy,
                            )
                        )
            present = tuple(item for item in inputs if item.state is MissingState.PRESENT)
            complete = len(present) == len(inputs) and len(present) >= spec.minimum_observations
            if spec.window_basis is WindowBasis.LATEST_VALUES:
                complete = complete and len(present) == len(spec.inputs)
            require(
                complete or spec.missing_input_policy is MissingInputPolicy.PROPAGATE,
                "insufficient/missing admissible computation inputs",
            )
            state = None
            if spec.normalization_state_id is not None:
                state = self.repository.get(NormalizationState, spec.normalization_state_id)
                require(
                    state.available_ns <= origin.availability_cutoff_ns
                    and state.fit_cutoff_ns <= origin.availability_cutoff_ns,
                    "future normalization state at forecast origin",
                )
                require(
                    clocks.final_available_ns >= state.available_ns,
                    "normalized result backdated",
                )
            require(
                all(
                    item.clocks.final_available_ns <= clocks.final_available_ns
                    for item in inputs
                ),
                "derived output before latest dependency availability",
            )
            require(
                clocks.afre_computed_ns >= origin.availability_cutoff_ns,
                "computation executed before its information cutoff",
            )
            values = tuple(item.value for item in present)
            assert all(value is not None for value in values)
            from typing import cast

            from afre.lineage import Scalar

            value = (
                transform(spec.transformation, cast(tuple[Scalar, ...], values), state)
                if complete
                else None
            )
            references: list[FeatureDependency] = []
            for feature in spec.inputs:
                matching = [item for item in inputs if item.feature == feature]
                if matching:
                    last = max(
                        matching,
                        key=lambda item: (item.clocks.final_available_ns, item.fingerprint),
                    )
                    projected = last.to_feature_value(
                        origin.instrument, last.state, self.policy.fingerprint
                    )
                else:
                    projected = self._projection(
                        FeatureAudit(
                            feature,
                            origin,
                            MissingState.MISSING,
                            None,
                            None,
                            "insufficient history",
                            self.policy,
                        )
                    )
                references.append(
                    FeatureDependency(
                        feature.definition.fingerprint,
                        projected.fingerprint,
                        projected.available_ns,
                    )
                )
            source = SourceReference(
                ProvenanceRef(
                    "AFRE-computation",
                    spec.fingerprint,
                    IMPLEMENTATION_VERSION,
                    bytes_digest(
                        (
                            spec.fingerprint
                            + origin.fingerprint
                            + "".join(item.fingerprint for item in inputs)
                        ).encode()
                    ),
                ),
                spec.output.source_dataset_ids[0],
                tuple(sorted({item.source.fingerprint for item in inputs})),
            )
            self.repository.put(source)
            # Computations across broadcast scopes must retain the exact source entity.
            entity, _ = resolve_entity(self.repository, spec.output, origin)
            require(entity is not None, "computation requires explicit output scope binding")
            assert entity is not None
            require(
                all(item.entity == entity for item in inputs),
                "computation output/input entity mismatch",
            )
            output = FeatureVintage(
                spec.output,
                entity,
                origin.timestamp_ns,
                clocks,
                source,
                value,
                MissingState.PRESENT if complete else MissingState.MISSING,
                DataQuality.VERIFIED,
                input_ids=tuple(item.fingerprint for item in inputs),
                dependency_refs=tuple(references),
                computation_spec_id=spec.fingerprint,
                normalization_state_id=spec.normalization_state_id,
            )
            self._authorize_delivery(output)
            self.repository.put(output)
            receipt = FeatureComputationReceipt(
                spec,
                origin,
                output.fingerprint,
                output.input_ids,
                clocks.availability_floor_ns,
                spec.normalization_state_id,
            )
            self.repository.put(receipt)
        return output, receipt

    def lineage(self, vintage_id: str) -> tuple[object, ...]:
        with self.repository.read_snapshot():
            return self.repository.lineage(vintage_id)

    def audit(self) -> int:
        with self.repository.read_snapshot():
            return self.repository.audit()
