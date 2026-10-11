# Immutable artifact registry

Registry entries record exact artifact/model IDs, native type and producer family, implementation version, target/horizon, creation and fitting cutoff when available, availability, schema, fingerprint and compatibility metadata. Each entry pins an anchor source forecast; its producer/target/horizon are the exact publication producer, rather than an incidental active model. Contributing native models retain their exact artifact identities.

The closed categories cover models, forecast artifacts, calibration, ranking, event/regime conditioning, mixtures, nonlinear and sequence models, uncertainty, orthogonalization, fusion, health snapshots, challenge programs/runs and forecast snapshots. Registration succeeds only for actual supported native artifacts. Registry is metadata, not deployment. Only AVAILABLE descriptive lifecycle metadata is supported; no service lifecycle transitions are implemented.

Every published forecast pins contributor entries. A separate deterministic snapshot registry entry references the completed snapshot, avoiding a circular fingerprint. A frozen `PublicationCatalog` includes both that entry and every contributor. Exact ID lookup and filtered artifact/producer/target/horizon listing use canonical fingerprint ordering.

Registry listing reads an explicit catalog fingerprint. Keyset `RegistryCursor` pins the entire `RegistryQuery` fingerprint and last entry ID; changing filters/page size/catalog invalidates the cursor. Concurrent appends cannot reorder a frozen catalog. The result bound is 100 per page; catalogs are bounded at 10,000 entries. No hidden latest or offset-based pagination exists.

See [retrieval](snapshot-retrieval.md) and [replay](service-reproducibility.md). AFRE-25 remains final integration/hardening.

Registry family labels identify native artifact families. The version is the native artifact implementation version when exposed, otherwise the 1.0 family contract version. Exact artifact/content IDs pin trained revisions and their native specifications; these descriptive labels do not select or deploy a model.
