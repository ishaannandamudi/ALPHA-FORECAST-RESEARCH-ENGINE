# Target contracts

`TargetSpec` is immutable and content-addressed. Supported target types are simple
return, log return, residual return, absolute return, realized volatility, downside
return, maximum adverse excursion and maximum favorable excursion. Residual
return requires a stable benchmark ID; other targets reject one. Implementations
and normalization of units are future label-engine concerns.

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

Future AFRE-2 must define admissible-price quality, close/auction conventions,
corporate-action timing, benchmark vintages, missing prices, delisting outcomes,
window gaps, endpoint resolvers and maximal input availability. It must retain raw
observation/adjustment lineage and test target completion at each fit cutoff.
