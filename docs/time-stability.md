# Time-window stability

Windows pin UTC start/end, endpoint inclusivity, minimum N and elapsed-time calendar semantics. No session calendar is inferred. Overlapping windows are supported and remain visible in fingerprints. Rolling windows use declared length/stride and a hard count limit; adaptive boundaries and change-point searches are absent. Expanding windows and refit schedules are deferred.

TEMPORAL_PANEL metrics summarize the exact declared observations. SAME_ORIGIN_CROSS_SECTION computes IC separately within each full time/universe/session/build context and averages valid origins equally. Different contexts at the same timestamp cannot be pooled. Insufficient or constant origin groups remain explicit in the result reason. These are descriptive cohort diagnostics, not a pooled temporal causal relationship.

Chronological trends use declared window centers, a descriptive least-squares slope per nanosecond and an explicit monotonicity label. Integer relative-center arithmetic preserves small intervals at large UTC epochs. Overlap and changing cohorts remain unadjusted; the trend is partially comparable and carries no significance inference. This is not AFRE-22 operational drift/decay or health automation.

TRAIN behavior is permitted through existing AFRE-5 later IN_SAMPLE forecasts, which remain historically inadmissible. The frozen fit is preserved. TRAIN, VALIDATION and sealed TEST can appear in explicitly declared descriptive populations; there is no environment-specific refit.
