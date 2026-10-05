# Provider-neutral external signals

The eventual handoff remains: external engine → neutral AFRE provider/structured
signal → AFRE FeatureVintage/source reference → forecasting or ranking. The downstream
HFT integration system owns AME→AFRE adapters. AFRE imports no AME package, reads no
external engine SQLite registry, assumes no sibling paths and copies no microstructure
algorithms. ExternalSignalProvider is a data protocol; no executable plugin loading
or network adapter is implemented in AFRE-9.

ExternalSignal pins provider name/version/schema, stable security, optional venue,
signal name/semantic version, as-of time, scalar value/unit, quality, exact immutable
SourceReference and fingerprint. It reuses upstream publication, upstream source
availability, AFRE receipt, ingestion, computation and final availability clocks.
Without qualified historical-delivery evidence, final availability cannot precede
actual AFRE computation/receipt. A provider event/publication timestamp alone never
establishes availability at the ranking origin.

Live publication at 10:00 with receipt at 10:02 cannot enter a 10:01 ranking. A months-
later archive is reconstructed later and cannot be silently backdated. Explicit
qualified reconstruction may establish earlier historical knowability while keeping
actual later physical clocks. The exact source/security proof must be persisted and
its attestor explicitly approved by CrossSectionSpec. This does not fabricate old
literal AFRE ingestion or old rank-emission time.

VALID signals with numeric scalar scores may rank. STALE, MISSING, UNSUPPORTED,
DEGRADED and INVALID remain typed and withheld. DEGRADED retains its supplied value
in the original external artifact but does not enter scores or the ordinary feature
bridge as verified data. Optional maximum age is supplied. Different versions or
semantic/unit identities cannot mix inside one external ordering.

`signal_feature` explicitly converts a matching security-scoped registered feature
definition into AFRE-1 FeatureVintage. Names, versions, units, source datasets and
types must agree. Categorical/numeric external regime/state data can be ordinary
causal features; there is no AFRE regime-conditioned model. Specialist predictions
remain external data and never impersonate AFRE-native fitted models. The existing
SourceReference/ProvenanceRef fulfills the external artifact-reference boundary.

Execution fields such as order IDs, live inventory, position sizes, pending orders
and execution decisions are rejected as declared signal-name components. The closed
scalar contract contains no executable payload, path, order structure or arbitrary
object. Metadata checks cannot discover a dishonest provider hiding execution/future
information in a scalar; adapter/provider audits remain necessary. No eval, exec,
pickle, joblib, shell, dynamic imports or runtime network occurs in the package.
All tests and fresh-process replay workers block sockets and DNS.

## AFRE-10 integration

AFRE-10 consumes exact neutral post-event reaction ScoreSpecs/ExternalSignals. Event availability does not establish reaction availability. Each reaction must be causally available, post-anchor and security/semantic compatible. EIE and AME remain external/provider-neutral; the downstream HFT system implements adapters.
See [event-conditioned forecasting](event-conditioned-forecasting.md).

## AFRE-11 composition boundary

[Regime conditioning](regime-conditioned-forecasting.md) consumes exact causal
filtered hard/soft state evidence without changing this phase's contracts. As-of
is distinct from all six availability clocks. TRAIN state means/fitted-residual
offsets, fixed soft weighting and explicit fallback are horizon-specific. Application
preserves exact base bytes and reads no truth. Matched evaluation/ranking retains
PIT scope and TEST controls. Global calibration cannot silently transfer, and
descriptive regime drift never refits. MCE/AME remain external neutral data producers;
downstream HFT integration supplies adapters. Predictive metrics do not prove profitability.
