# Exact horizon sets

`HorizonSet` pins one exact AFRE-2 TargetDefinition for each AFRE-0 ForecastHorizon.
The target includes endpoint policy, calendar, bar stream, adjustment, family and
implementation version. Duplicate semantic horizons reject, even if target names
are different. Free-form labels such as “5m” cannot substitute for typed identity.

COMPARABLE_DURATION sorts elapsed nanoseconds or counts only within the same
basis, calendar, stream, endpoint convention and session policy. Session counts use the supplied
calendar; bar counts use the supplied observation stream. A session is never
converted into 24 hours. Mixed bases or incompatible calendars require
EXPLICIT_CANONICAL order. In that mode supplied order is semantic: reversing it
changes identity. Weights and output vectors always follow that canonical order.

Rich target mapping and exact feature/model bindings are validated on publication.
One target cannot be copied across different horizons. Foundation target semantics
remain unchanged: richer AFRE-2 endpoint rules are composed explicitly.

Within a horizon quantiles stay ordered. Across horizons quantiles, expected
returns and variances need not be monotone. Missing entries retain their target
identity and never shorten a vector silently.
