"""Frozen exact selections and computation receipts, separate from mutable queries."""

from dataclasses import dataclass

from afre.datasets import ForecastFeatureRow
from afre.feature_store.dag import FeatureComputationSpec
from afre.feature_store.models import FeatureVintage, RegisteredFeatureDefinition
from afre.feature_store.schema import QueryPolicy, StoreScope
from afre.features import MissingState
from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require


@contract("fs_computation_receipt")
@dataclass(frozen=True, slots=True)
class FeatureComputationReceipt(Artifact):
    spec: FeatureComputationSpec
    origin: ForecastOrigin
    output_id: str
    input_ids: tuple[str, ...]
    computation_available_ns: int
    normalization_state_id: str | None

    def _normalize(self) -> None:
        require(len(set(self.input_ids)) == len(self.input_ids), "duplicate receipt input")
        object.__setattr__(self, "input_ids", tuple(sorted(self.input_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.output_id, "fs_vintage")
        for identity in self.input_ids:
            validate_fingerprint(identity, "fs_vintage")
        require(
            self.normalization_state_id == self.spec.normalization_state_id,
            "receipt normalization state mismatch",
        )
        require(
            self.spec.output.build_context == self.origin.build_context
            and self.computation_available_ns >= self.origin.availability_cutoff_ns,
            "receipt computation context/cutoff mismatch",
        )


@contract("fs_feature_audit")
@dataclass(frozen=True, slots=True)
class FeatureAudit(Artifact):
    feature: RegisteredFeatureDefinition
    origin: ForecastOrigin
    state: MissingState
    selected: FeatureVintage | None
    scope_binding_id: str | None
    reason: str
    query_policy: QueryPolicy

    def _validate(self) -> None:
        if self.scope_binding_id is not None:
            validate_fingerprint(self.scope_binding_id, "fs_scope_binding")
        if self.selected is not None:
            require(self.selected.feature == self.feature, "audit definition mismatch")
            require(
                self.selected.clocks.final_available_ns <= self.origin.availability_cutoff_ns,
                "audit selected future vintage",
            )
            require(
                self.state == self.selected.state
                or (
                    self.selected.state is MissingState.PRESENT
                    and self.state is MissingState.STALE
                ),
                "audit state disagrees with selected vintage",
            )
            if self.feature.scope is StoreScope.SECURITY:
                require(
                    self.selected.entity == self.origin.instrument
                    and self.scope_binding_id is None,
                    "audit security identity mismatch",
                )
            else:
                require(self.scope_binding_id is not None, "audit broadcast lacks binding")
        else:
            require(
                self.state
                in (
                    MissingState.MISSING,
                    MissingState.NOT_APPLICABLE,
                    MissingState.NOT_AVAILABLE_YET,
                ),
                "audit claims a value without a selected vintage",
            )


@contract("fs_join_result")
@dataclass(frozen=True, slots=True)
class PointInTimeJoinResult(Artifact):
    row: ForecastFeatureRow
    audits: tuple[FeatureAudit, ...]

    def _normalize(self) -> None:
        self.ordered("audits", "fingerprint")

    def _validate(self) -> None:
        require(len(self.audits) == len(self.row.features), "incomplete join audit")
        require(
            all(item.origin == self.row.origin for item in self.audits), "audit origin mismatch"
        )
        require(
            {item.feature.definition.fingerprint for item in self.audits}
            == {item.definition.fingerprint for item in self.row.features},
            "audit feature mismatch",
        )
        values = {item.definition.fingerprint: item for item in self.row.features}
        for audit in self.audits:
            projected = values[audit.feature.definition.fingerprint]
            require(projected.missing_state == audit.state, "join/audit state mismatch")
            if audit.selected is not None:
                require(
                    projected
                    == audit.selected.to_feature_value(
                        self.row.origin.instrument, audit.state, audit.query_policy.fingerprint
                    ),
                    "join value does not pin the audited exact vintage",
                )


@contract("fs_materialization")
@dataclass(frozen=True, slots=True)
class FeatureMaterialization(Artifact):
    results: tuple[PointInTimeJoinResult, ...]
    created_ns: int
    implementation_version: str

    def _normalize(self) -> None:
        self.ordered("results", "fingerprint")

    def _validate(self) -> None:
        require(bool(self.results), "empty feature materialization")
        require(
            len({item.row.origin.fingerprint for item in self.results}) == len(self.results),
            "duplicate materialization origin",
        )
        require(
            self.created_ns >= max(item.row.origin.timestamp_ns for item in self.results),
            "materialization creation precedes query origins",
        )
        require(
            all(
                audit.selected is None
                or self.created_ns >= audit.selected.clocks.afre_computed_ns
                for result in self.results
                for audit in result.audits
            ),
            "materialization creation precedes physical reconstruction/computation",
        )
