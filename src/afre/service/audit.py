"""Public audit pins the entire snapshot, registration and bounded forecast lineage."""

from dataclasses import dataclass

from afre.schema import Artifact, contract, require
from afre.service.registry_entries import RegistryEntry
from afre.service.snapshots import ForecastSnapshot
from afre.service.versions import VersionInfo, version_info


@contract("svc_audit")
@dataclass(frozen=True, slots=True)
class SnapshotAudit(Artifact):
    snapshot: ForecastSnapshot
    snapshot_registry_entry: RegistryEntry
    versions: VersionInfo
    limitations: tuple[str, ...]
    outcomes_read: bool = False
    action: str = "NONE_DESCRIPTIVE_ONLY;MANUAL_ONLY"

    def _validate(self) -> None:
        require(
            self.snapshot_registry_entry.artifact_id == self.snapshot.fingerprint
            and not self.outcomes_read
            and self.action == "NONE_DESCRIPTIVE_ONLY;MANUAL_ONLY"
            and self.versions == version_info(),
            "audit identity/boundary corruption",
        )


def audit_for(snapshot: ForecastSnapshot, entry: RegistryEntry) -> SnapshotAudit:
    return SnapshotAudit(
        snapshot,
        entry,
        version_info(),
        (
            "TRAIN fitted artifacts are immutable metadata leaves; service never refits",
            "historical health/challenge metadata is descriptive and does not read "
            "outcome truth",
            "TargetVintage, later outcome evaluations and TEST truth were not read",
            "rank is research output; predictive metrics do not establish trading "
            "profitability",
            "no deployment, training, promotion, portfolio, risk optimization or execution",
        ),
    )
