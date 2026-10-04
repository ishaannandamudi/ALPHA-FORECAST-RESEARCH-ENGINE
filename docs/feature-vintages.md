# Feature vintages and availability evidence

`RegisteredFeatureDefinition` wraps an unchanged AFRE-0 `FeatureDefinition` with
validated namespace, store scope, validity/freshness policy, calendar, build,
adjustment, exact source datasets and immutable parameters. Registry name/version
and foundation definition identity are unique. Changed definition logic requires
a new version/fingerprint. A computation logic index rejects a different trusted
transformation, input order, window, implementation, minimum history or missing
policy under an already bound output definition. Supplied normalization state
revisions remain independent artifacts pinned by each computation specification.

`FeatureVintage` contains the exact registered definition, stable entity,
effective time, optional interval end, source, value/state/quality, predecessor,
input vintage IDs, dependency references, computation spec and normalization state.
Changing any field creates another immutable identity. Revisions must retain the
same definition/entity/effective interval and cannot precede their predecessor's
availability. Storage never overwrites a vintage.

## Six availability clocks

| Field in AvailabilityEvidence | Meaning |
| --- | --- |
| upstream_publication_ns | Publication time evidenced by the upstream source; optional |
| upstream_available_ns | Earliest upstream delivery-channel availability evidenced; optional |
| afre_received_ns | Actual AFRE observation/receipt of the supplied information |
| afre_ingested_ns | Actual AFRE ingestion of the supplied information |
| afre_computed_ns | Actual extraction/computation or later reconstruction completion |
| final_available_ns | Earliest permitted use of this exact feature vintage |

Unavailable upstream clocks remain `None`; they are not inferred from receipt.
AFRE receipt <= ingestion <= computation. If upstream publication and source
availability both exist, publication <= source availability <= physical receipt.
For live ingestion and unqualified reconstruction, final availability is at least
actual AFRE computation, and therefore at least actual receipt, plus all evidenced
upstream constraints. A provider timestamp is never automatically AFRE availability.

Publication at 10:00 with receipt at 10:02 cannot serve origin 10:01. A historical
archive published at 10:00 but downloaded months later is unavailable to a
10:01 causal query unless independently qualified delivery evidence exists.
Marking it RECONSTRUCTED alone grants no earlier availability.

## Qualified reconstruction

`QualifiedHistoricalDelivery` pins the exact source fingerprint and entity,
evidence kind, historical channel receipt/ingestion/computation bounds,
qualification time, channel, attestor and qualification version. Historical
receipt must follow evidenced upstream availability; all historical processing
clocks are ordered. Qualification must precede physical reconstruction completion.
The local `QueryPolicy` must approve the attestor on append and historical use.

Only RECONSTRUCTED records may substitute this qualified historical processing
bound for their later physical processing bound. Final availability must still
follow upstream clocks and every input/state used. Actual later AFRE receipt,
ingestion and computation fields remain unchanged. QUALIFIED_CHANNEL_REPLAY
establishes availability to a qualified historical channel; it does not claim
that this AFRE instance literally received or ingested those bytes then.
AFRE_DELIVERY_LOG is a distinct evidence kind for a literal historical delivery.

AFRE-0 `FeatureValue.observed_ns` continues to mean upstream/source observation,
not AFRE receipt. Its projection refers to the full vintage to preserve these
six-clock distinctions. No physical receipt is silently clipped to an earlier
historical availability. Materialization creation must follow the selected
vintages' actual physical computation/reconstruction times.

## Absence and freshness

PRESENT includes numeric zero. MISSING, NOT_APPLICABLE, NOT_AVAILABLE_YET, STALE,
INVALID and UNKNOWN preserve separate explicit states with no invented numeric
substitute. NaN/infinity and boolean-as-number are rejected. Freshness is NEVER,
maximum elapsed age from EFFECTIVE_TIME or SOURCE_AVAILABILITY. Age equal to the
limit is fresh; age greater than the limit is stale. Source availability falls
back conservatively to final availability when absent. Session/count aging is
not implemented. Staleness qualifies a retained audit vintage independently of
its value; row projection withholds stale numerics to preserve AFRE-0 semantics.
