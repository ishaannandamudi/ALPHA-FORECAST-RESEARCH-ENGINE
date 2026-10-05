# External regime integration

MCE and AME/HFT outputs are translated by the **downstream HFT integration layer**
into provider-neutral AFRE RegimeProviderReference/RegimeTaxonomy/RegimeSnapshot data.
AFRE consumes broad market/macro/volatility/risk states and neutral liquidity or
microstructure states without owning their detectors. The offline demo uses invented
providers only. RegimeProvider is a structural data protocol, not a plugin loader.

No direct MCE dependency, no direct AME dependency, sibling imports/paths, private
SQLite reads, HMM copies, internal upstream types or executable provider payloads
exist. The earlier MarketContextProvider and AFRE-1 MarketContextFeatureProvider
remain ordinary neutral feature-delivery boundaries; SourceReference is reused.
Providers have no control over repository paths, executable imports or runtime I/O.

Adapters must supply exact taxonomy ordering/version, state semantics, scope/subject,
quality and all available clock evidence. A provider timestamp is never automatically
AFRE availability. Live use cannot precede receipt; qualified reconstruction must
preserve actual later reconstruction and exact locally approved historical evidence.
The contracts cannot independently authenticate a provider's records.

Bounded canonical JSON, strict typed validation, domain-separated fingerprints,
immutable transactional persistence and audit are the AFRE boundary. Learned regime
inference/gating is absent. Portfolio construction, risk optimization and execution
remain separate downstream projects; predictive metrics do not prove profitability.
