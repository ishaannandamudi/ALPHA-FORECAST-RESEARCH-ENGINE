"""Target truth artifacts, distinct from foundation/feature values."""

from dataclasses import dataclass

from afre.datasets import UniverseManifest
from afre.feature_store.models import AvailabilityEvidence
from afre.features import MissingState
from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition, TargetSetManifest
from afre.target_engine.quality import TargetQuality
from afre.target_engine.schema import BUILDER_VERSION
from afre.time import TimeRange
from afre.version import ENGINE_VERSION


@contract("target_vintage")
@dataclass(frozen=True, slots=True)
class TargetVintage(Artifact):
    definition: TargetDefinition
    origin: ForecastOrigin
    source_build_id: str
    window: TimeRange | None
    origin_bar_id: str | None
    endpoint_bar_id: str | None
    path_ids: tuple[str, ...]
    action_ids: tuple[str, ...]
    benchmark_id: str | None
    value: float | None
    state: MissingState
    completion_ns: int | None
    clocks: AvailabilityEvidence
    quality: TargetQuality
    reason: str
    builder_version: str = BUILDER_VERSION

    def _normalize(self) -> None:
        require(
            len(set(self.path_ids)) == len(self.path_ids), "duplicate target path observation"
        )
        require(len(set(self.action_ids)) == len(self.action_ids), "duplicate target action")
        object.__setattr__(self, "action_ids", tuple(sorted(self.action_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.source_build_id, "target_source_build")
        for identity in (self.origin_bar_id, self.endpoint_bar_id, *self.path_ids):
            if identity is not None:
                validate_fingerprint(identity, "target_bar")
        for identity in self.action_ids:
            validate_fingerprint(identity, "target_action")
        if self.benchmark_id is not None:
            validate_fingerprint(self.benchmark_id, "target_benchmark_return")
        require(
            (self.value is not None) == (self.state is MissingState.PRESENT),
            "target value/absence state mismatch",
        )
        require(self.state is not MissingState.STALE, "target staleness is a quality dimension")
        require(
            self.clocks.historical_delivery is None,
            "target computation cannot silently backdate reconstructed labels",
        )
        if self.window is not None:
            require(
                self.window.start_ns == self.origin.timestamp_ns,
                "target origin/window mismatch",
            )
        if self.state is MissingState.PRESENT:
            require(
                self.window is not None
                and self.origin_bar_id is not None
                and self.endpoint_bar_id is not None
                and self.completion_ns is not None,
                "present target lacks endpoint/completion evidence",
            )
            assert self.window is not None and self.completion_ns is not None
            require(
                self.completion_ns >= self.window.end_ns
                and self.clocks.final_available_ns >= self.completion_ns,
                "target available before completion",
            )
        require(
            self.builder_version == self.definition.implementation_version,
            "target builder/definition version mismatch",
        )


@contract("target_dataset")
@dataclass(frozen=True, slots=True)
class TargetDatasetManifest(Artifact):
    name: str
    origins: tuple[ForecastOrigin, ...]
    universe: UniverseManifest
    targets: TargetSetManifest
    source_build_id: str
    row_ids: tuple[str, ...]
    build_cutoff_ns: int
    constructed_ns: int
    builder_version: str = BUILDER_VERSION
    engine_version: str = ENGINE_VERSION

    def _normalize(self) -> None:
        self.ordered("origins", "fingerprint")
        require(len(set(self.row_ids)) == len(self.row_ids), "duplicate target dataset row")
        object.__setattr__(self, "row_ids", tuple(sorted(self.row_ids)))

    def _validate(self) -> None:
        validate_fingerprint(self.source_build_id, "target_source_build")
        require(
            bool(self.origins)
            and len(self.row_ids) == len(self.origins) * len(self.targets.definitions),
            "incomplete target dataset grid",
        )
        require(
            self.constructed_ns >= self.build_cutoff_ns,
            "target dataset constructed before data cutoff",
        )
        for origin in self.origins:
            require(
                origin.universe_id == self.universe.fingerprint,
                "target dataset universe mismatch",
            )
        for identity in self.row_ids:
            validate_fingerprint(identity, "target_vintage")


@contract("target_audit")
@dataclass(frozen=True, slots=True)
class TargetAudit(Artifact):
    vintage: TargetVintage
    lineage_ids: tuple[str, ...]

    def _normalize(self) -> None:
        require(
            len(set(self.lineage_ids)) == len(self.lineage_ids),
            "duplicate target audit lineage",
        )
        object.__setattr__(self, "lineage_ids", tuple(sorted(self.lineage_ids)))
