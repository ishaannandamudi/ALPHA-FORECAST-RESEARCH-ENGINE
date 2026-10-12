# Provider-neutral downstream handoff

[downstream_client.py](../examples/downstream_client.py) is an offline illustrative adapter/consumer, not a real integration. `NeutralObservation` requires an explicit stable security ID, UTC epoch nanoseconds, unit, quality, publication/source-availability/observed/ingested/computed/final clocks. Adapter validation rejects unit mismatches and receipt/processing backdating. Tickers are display information, never identity. The adapter does not assert qualified historical reconstruction; that requires the separate existing proof contract and approved local policy.

An administrator publishes snapshots from native causal evidence. Consumers negotiate API 1.0/capabilities, request exact snapshot IDs or frozen selectors, preserve output target/horizon/unit and law semantics, handle stable unavailability/errors, and compare a corrected identity explicitly while retaining the original. Reopen the store and replay canonical bytes under the pinned version catalog. No source-provided filesystem path is accepted.

AME, MCE, EIE, options engines and HFT repositories are neither imported nor required. External providers must implement neutral contracts without reading their internal databases through AFRE. No network, credentials or broker setup is required. Risk optimization, portfolio allocation and execution are owned downstream. No forecasting engine guarantees trading profitability.

Review [the release manifest](afre-release-manifest.json), [release notes](AFRE_RELEASE_NOTES.md), [security assumptions](AFRE_SECURITY_AUDIT.md) and [reproducibility scope](AFRE_REPRODUCIBILITY_AUDIT.md) before adoption. This is a research release candidate only after all recorded final gates pass; production deployment requires separate evidence.
