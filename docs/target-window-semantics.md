# Exact target windows

For origin T and elapsed horizon H, the nominal outcome interval is **(T,T+H]**.
`TimeRange` stores these boundary numbers; ordinary `TimeRange.contains` is not
used to interpret label price inclusion. Target start equals the forecast origin.
P0 is an explicit reference price selected separately from the future path. The
default AFRE-2 rule is an exact completed close at T and an exact close at T+H.
The foundation TargetSpec still uses its original first-after-origin convention;
it is not silently converted into this richer AFRE-2 definition.

| Selection | Direction and bound |
| --- | --- |
| Exact origin/endpoint | Exact completion time, tolerance zero |
| Last at or before origin | Completion in [T−origin_tolerance,T] |
| First strictly after origin | Completion in (T,T+origin_tolerance]; positive explicit tolerance |
| Last at or before endpoint E | Completion in [E−endpoint_tolerance,E] |
| First at or after endpoint E | Completion in [E,E+endpoint_tolerance] |

No arbitrary nearest bar is used. Tolerance rules, units, direction and bounds are
fingerprinted, and deviations generate typed quality flags. Actual selected P0/P1
times remain auditable. A selected endpoint must be strictly later than selected
P0; tolerating Friday's close for both sides does not fabricate a weekend return.
Window completion is max(nominal endpoint, actual selected endpoint), so an early
tolerated price does not close the future window early. Label completion additionally
waits for all required input availability/physical processing. Missing prints do not silently
skip to a later positive bar; the selected explicit missing observation fails closed.

Elapsed horizons use UTC nanoseconds, including closed markets. Session horizons
count the next N supplied session **closes strictly after T**, including the current
session's close when T is inside it. At a session close the next session is counted.
T must lie in its declared session. Holidays, weekends, DST and shortened sessions
come exclusively from a versioned, supplied nonoverlapping UTC schedule. Exchange
timezone text is metadata, not a hidden calendar resolver. No network calendar or
24-hour approximation exists. REGULAR_ONLY excludes marked extended sessions;
INCLUDE_EXTENDED explicitly admits them and counts their closes.

Bar horizons count N declared completed source observations strictly after T within
the frozen build. Explicit missing/halted observations count as stream observations
and then produce their declared missing outcome if selected. Gaps with no record do
not count as synthetic bars. A source interval, calendar grid and stream version are
required; a human string such as “5m” does not resolve a stream.

Path estimators require exact origin and endpoint. The positive sampling interval
must be a multiple of the source interval, and T must align to the supplied session
sampling grid. Expected future sample closes exclude T and include the endpoint.
Calendar closures generate no expected observations. A short terminal interval is
not silently invented. Default FAIL_MISSING requires all positive samples and an
aligned endpoint. MINIMUM_COVERAGE requires explicit minimum count/fraction; a
partial path is flagged and withheld from training. Missing intervals break the
volatility return chain: there is no jump return bridging an absent print. Between
valid closes across a declared closure, the close-to-close return is retained as
part of the supplied trading grid. Excursions evaluate retained sampled closes.

Every row records origin, nominal start/end, actual source endpoints, completion
and availability. SQLite interval indexes support later overlap detection; AFRE-4
will implement purging/embargo. AFRE-2 does not generate split folds.
