"""Service-wide limits checked before projection, replay and query expansion."""

from dataclasses import dataclass, fields

from afre.schema import Artifact, contract, require


@contract("svc_bounds")
@dataclass(frozen=True, slots=True)
class ServiceBounds(Artifact):
    artifacts: int = 100000
    registry_entries: int = 10000
    page_size: int = 100
    horizons: int = 32
    contexts: int = 8
    context_fields: int = 4096
    event_refs: int = 128
    atoms: int = 10000
    components: int = 32
    lineage_nodes: int = 10000
    lineage_depth: int = 64
    payload_bytes: int = 8 * 1024 * 1024
    lineage_bytes: int = 8 * 1024 * 1024
    snapshot_bytes: int = 128 * 1024 * 1024

    def _validate(self) -> None:
        ceilings = ServiceBounds.__dataclass_fields__
        for f in fields(self):
            require(
                0 < getattr(self, f.name) <= ceilings[f.name].default,
                "service configured bound exceeds hard ceiling",
            )


def ids(value: Artifact, *names: str) -> None:
    from afre.ids import validate_fingerprint

    for name in names:
        items = getattr(value, name)
        require(len(set(items)) == len(items), "duplicate service references")
        for identity in items:
            validate_fingerprint(identity)
        object.__setattr__(value, name, tuple(sorted(items)))
