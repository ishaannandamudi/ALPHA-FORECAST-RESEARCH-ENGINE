# AFRE service API 1.0

Consumers import the supported contracts from `afre.service` and depend on `ForecastServiceProvider`. An application bootstrap supplies a repository to `ForecastResearchService` (alias `AFREService`); consumer queries contain IDs and typed selectors, never filesystem paths or SQL. Public API != internal DB: consumers need no private modules, table layouts, or filesystem inspection.

The read-only methods are `get_snapshot`, `get_snapshot_for_origin`, `get_multi_horizon_snapshot`, `get_registry_entry`, `get_registry_entry_for_artifact`, `list_registry_entries`, `get_health_metadata`, `get_challenge_metadata`, `get_audit`, `get_version_info` and `get_capability_catalog`. Every call returns a canonical `ServiceReply` with status, typed value, API version and service schema. Publication is a separate explicit `SnapshotPublisher` capability; it validates, persists and indexes only.

```python
from afre.service import ForecastServiceProvider, ServiceStatus


def read_exact(provider: ForecastServiceProvider, identity: str) -> None:
    result = provider.get_snapshot(identity, ("POINT",))
    if result.status is ServiceStatus.AVAILABLE:
        print(result.value)
```

There are no training, fitting, selection, recalibration, promotion, rollback, activation, allocation or execution methods. This is an in-process provider-neutral façade with zero runtime dependencies and no network daemon. Downstream adapters translate these public contracts; direct external-engine imports and broker integrations are outside AFRE.

See [retrieval](snapshot-retrieval.md), [errors](service-errors.md), [versions](service-versioning.md) and [context](snapshot-context.md). AFRE-25 remains final hardening.
