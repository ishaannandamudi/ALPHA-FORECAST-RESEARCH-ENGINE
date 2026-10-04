# Target contracts

`TargetSpec` is immutable and content-addressed. Supported target types are simple
return, log return, residual return, absolute return, realized volatility, downside
return, maximum adverse excursion and maximum favorable excursion. Residual
return requires a stable benchmark ID; other targets reject one. Implementations
and normalization of units are handled separately by the additive AFRE-2 target engine.

Each target embeds a typed horizon. Internal duration/count/calendar/endpoint
fields determine identity; human descriptions such as “1d” do not. A one-day
elapsed target is distinct from a one-session target and has different DST and
holiday implications.

The foundation target price convention is **(T, endpoint]**: first admissible
price strictly after origin through last admissible price at/before endpoint.
`ForecastTargetRow.window.start_ns` must equal T. Elapsed endpoint must equal
T plus the horizon duration. Nonelapsed endpoints require an explicit resolver
artifact fingerprint. The row retains value, availability, market dataset ID and
quality. Target windows are not ordinary half-open price-selection intervals even
though `TimeRange` stores their boundary numbers.

A target's availability cannot precede endpoint completion. Training cannot use it
until both completion and data availability, and only verified nonmissing labels
qualify. The dataset must declare the target and market source. Values from future
windows cannot be features; contracts and hash namespaces separate both families.
AFRE-0 does not calculate prices, returns, volatility, residuals or excursions.

AFRE-2 supplies these concerns in [forecast targets](forecast-targets.md), with
explicit close sampling, window selection, source/action/benchmark vintages,
availability and quality. `afre.target_engine.TargetDefinition` is a distinct
contract; it defaults to exact P0 at T and does not reinterpret the foundation
first-after-T rule. Rich target policies cannot silently become TargetSpec or feature
values. Foundation contracts and serialized schemas remain unchanged. See
[windows](target-window-semantics.md) and [lineage](target-lineage.md).
