"""Immutable publication identity includes every requested context section."""

from dataclasses import dataclass

from afre.forecast import ForecastOrigin
from afre.schema import Artifact, contract, require
from afre.service.bounds import ids
from afre.service.context import SnapshotContext
from afre.service.outputs import ForecastOutput
from afre.service.queries import SnapshotPublication
from afre.service.schema import SnapshotBundleStatus, SnapshotMode
from afre.service.versions import SUPPORTED_ENGINES
from afre.target_engine.definitions import TargetDefinition
from afre.universe.identity import StableSecurityId
from afre.version import ENGINE_VERSION


@contract("svc_lineage")
@dataclass(frozen=True, slots=True)
class SnapshotLineage(Artifact):
    root_id: str
    node_ids: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    bytes_checked: int
    reconstruction_evidence_ids: tuple[str, ...]
    policy: str = "forecast-evidence-no-outcome-expansion-v1"

    def _normalize(self) -> None:
        ids(self, "node_ids", "reconstruction_evidence_ids")
        object.__setattr__(self, "edges", tuple(sorted(set(self.edges))))

    def _validate(self) -> None:
        require(
            self.root_id in self.node_ids
            and len(self.node_ids) <= 10000
            and self.bytes_checked <= 8 * 1024 * 1024,
            "lineage root/node/byte bound",
        )
        require(
            all(a in self.node_ids and b in self.node_ids for a, b in self.edges)
            and self.policy == "forecast-evidence-no-outcome-expansion-v1",
            "lineage edge policy",
        )


@contract("svc_snapshot")
@dataclass(frozen=True, slots=True)
class ForecastSnapshot(Artifact):
    publication: SnapshotPublication
    security: StableSecurityId
    origin: ForecastOrigin
    target: TargetDefinition
    producer_id: str
    model_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    universe_id: str
    output: ForecastOutput
    contexts: tuple[SnapshotContext, ...]
    registry_entry_ids: tuple[str, ...]
    lineage: SnapshotLineage
    final_available_ns: int
    mode: SnapshotMode
    engine_version: str = ENGINE_VERSION
    store_version: str = "1.24"
    api_version: str = "1.0"
    snapshot_schema: str = "1.0"

    def _normalize(self) -> None:
        ids(self, "model_ids", "source_ids", "registry_entry_ids")
        self.ordered("contexts", "fingerprint")

    def _validate(self) -> None:
        require(
            self.engine_version in SUPPORTED_ENGINES
            and self.store_version == "1.24"
            and self.api_version == self.snapshot_schema == "1.0",
            "snapshot version mismatch",
        )
        require(
            self.output.target_id == self.target.fingerprint
            and self.output.horizon_id == self.target.horizon.fingerprint
            and self.producer_id == self.output.producer_id
            and self.security.instrument == self.origin.instrument,
            "snapshot output identity",
        )
        require(
            self.output.available_ns
            <= self.final_available_ns
            <= self.origin.availability_cutoff_ns
            and self.publication.published_ns >= self.final_available_ns,
            "snapshot causal availability/publication",
        )
        require(
            len(self.contexts) == len(self.publication.contexts)
            and all(
                c.available_ns
                <= (
                    self.publication.published_ns
                    if c.historical_evaluation
                    else self.final_available_ns
                )
                for c in self.contexts
            ),
            "snapshot context availability",
        )

    @property
    def snapshot_id(self) -> str:
        return self.fingerprint

    @property
    def etag(self) -> str:
        return self.fingerprint


@contract("svc_bundle")
@dataclass(frozen=True, slots=True)
class MultiHorizonSnapshot(Artifact):
    requested_horizon_ids: tuple[str, ...]
    snapshots: tuple[ForecastSnapshot, ...]
    missing: tuple[tuple[str, str], ...]
    status: SnapshotBundleStatus

    def _normalize(self) -> None:
        ids(self, "requested_horizon_ids")
        self.ordered("snapshots", "snapshot_id")
        object.__setattr__(
            self,
            "snapshots",
            tuple(
                sorted(
                    self.snapshots, key=lambda s: (s.target.horizon.fingerprint, s.snapshot_id)
                )
            ),
        )
        object.__setattr__(self, "missing", tuple(sorted(self.missing)))

    def _validate(self) -> None:
        horizons = tuple(s.target.horizon.fingerprint for s in self.snapshots)
        absent = tuple(h for h, _ in self.missing)
        require(
            len(self.requested_horizon_ids) <= 32
            and len(set(horizons)) == len(horizons)
            and len(set(absent)) == len(absent)
            and set(horizons).isdisjoint(absent)
            and set(horizons + absent) == set(self.requested_horizon_ids),
            "bundle exact horizon grid",
        )
        expected = (
            SnapshotBundleStatus.COMPLETE
            if not absent
            else (
                SnapshotBundleStatus.PARTIAL if horizons else SnapshotBundleStatus.UNAVAILABLE
            )
        )
        require(self.status is expected, "bundle status mismatch")
        require(
            len({(s.security, s.origin) for s in self.snapshots}) <= 1,
            "independent horizon snapshots require matching origin/security",
        )
