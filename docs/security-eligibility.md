# Historical security eligibility

Eligibility is separate from membership. `EligibilityPolicy` is immutable and
part of UniverseDefinition identity: security types, venues, countries, currencies,
primary/explicit listing, active/extended session, minimum completed listing
sessions, minimum market observations, price/liquidity thresholds, feature IDs,
lookback and explicit missing-data rule. Changing it requires another semantic
name/version. No rule is inferred from current security metadata.

`EligibilityResult` returns ELIGIBLE, INELIGIBLE, NOT_APPLICABLE,
NOT_AVAILABLE_YET, UNKNOWN or CONFLICTED with typed reason and exact listing,
universe/security/relationship/lifecycle/calendar and market evidence. Evaluation
is ordered and returns its first failing rule; successful results explain PASSED.
An excluded member remains represented with NOT_MEMBER. Missing/stale data is
UNKNOWN by default; explicit missing_rule=INELIGIBLE opts into exclusion.

Market inputs are exact AFRE-1 registered SECURITY/LAST_OBSERVATION vintages.
Currency units, build context, adjustment and calendar must agree. Adjustments
cannot be known after min(T,known_as_of). Each completed effective observation
selects latest admissible revision using AFRE-1 predecessor/tie logic, freshness,
quality and delivery qualification. The latest completed effective price is the
threshold price. This is a market observation series, not a new generic feature
selector. Target-only source/label objects cannot enter it.

All market inputs require effective time <= T and final availability <=
min(T,known_as_of). Price must be positive, PRESENT, numeric and VERIFIED. The
trailing window is exactly (T-lookback_ns,T], measured in elapsed UTC nanoseconds.
Share volume is the finite sum of nonnegative completed volumes. Mean dollar
volume is sum(price_at_observation × shares_at_observation)/observation_count,
using exact effective-time alignment and the configured minimum observation count.
Missing alignment, missing/unverified volume or revision ambiguity is explicit;
there is no forward fill, imputation, partial-window extrapolation or implicit FX.

Listing age counts only supplied completed calendar sessions whose start is after
listing start and end <= min(T,known_as_of). Market observation count is independent.
Regular/extended sessions use explicit half-open intervals; extended sessions are
excluded unless selected. Listing/calendar venue mismatch is NOT_APPLICABLE.
Price currency mismatch cannot compare a USD threshold to EUR information.

Historical HALTED, SUSPENDED, DELISTED and UNKNOWN states remain separate. A known
valid delisting is checked even after its listing interval has ended. RELISTING
can supersede earlier terminal lifecycle state; tied contrary events conflict.
Merger/spinoff relationships never transfer old observations to another security.
No borrow, short availability, risk optimization, portfolio construction or
execution exists. Eligibility does not claim trading profitability.
