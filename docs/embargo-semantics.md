# Embargo semantics

EmbargoPolicy records ELAPSED_TIME, TRADING_SESSIONS or BARS, a nonnegative count,
and AFTER (default), BEFORE or BOTH. Count zero disables fences. All origin fences
are [start,end): the first embargoed instant is included and the release instant is
excluded. A target purge and an origin embargo are separate checks.

Elapsed count is UTC nanoseconds. BEFORE protects [validation start − count,start),
clipped at zero; AFTER protects [validation end,end + count). TEST has the same
fences. Session count uses an exact persisted AFRE-3 UniverseCalendar fingerprint,
version, source and regular-session schedule. BEFORE counts the last complete sessions
whose close <= protected start; AFTER counts the first sessions whose open >= protected
end. Fences include overnight gaps, holidays and short sessions between the anchor
and the chosen supplied session endpoint. Extended sessions are excluded explicitly.

BARS uses EmbargoBarGrid with named calendar, stream, version, neutral source,
known time and nonoverlapping declared bar periods. The same complete-before and
start-after rules count actual periods. Neither sessions nor bars become elapsed
calendar days. Insufficient schedule coverage, a future calendar/grid or a mismatched
dataset calendar/source/target-bar stream fails. The supplied grid is a declared research contract, not an
inferred executable provider path.

Fences include all validation windows in the declared fold collection plus its
common TEST range. Thus AFTER fences around a previous validation window protect
that window when a later walk-forward fold admits older origins to training. Current
TRAIN still precedes current validation; an AFTER-only current-window fence can be
inactive in an isolated chronological holdout. BEFORE and BOTH can protect the gap
immediately before the current validation window. Purging takes precedence when both
rules exclude the same sample. Membership stores the chosen exclusion reason.
