# Cross-sectional redundancy

CROSS_SECTIONAL_HISTORICAL fits one projection across complete same-origin eligible TRAIN security
grids, then applies frozen coefficients to securities within later origins. This is distinct from
fitting coefficients on each evaluated cross-section. Per-origin fitting is unsupported and is not
advertised as a forecasting transform. No target is read during residual construction.

Each row must pin the exact AFRE-3 eligibility result and snapshot. The snapshot must project exactly
to the ForecastOrigin's foundation universe manifest, timestamp, information cutoff, session and
build context. Complete eligible security membership is checked for every TRAIN group and held-out
cross-sectional evaluation group. Mixing origin/universe contexts, missing a grid security or using
current constituents fails. Missing signal values retain explicit states; metrics use a documented
common complete-case intersection within the pinned full grid.

`engine.rank(template, residual_ids, groups)` creates explicit AFRE-9 external score sources with
exact residual/projection provenance, units, actual clocks and target/horizon. AFRE-9 retains its
peer transforms, tied ranks, quality policy, eligible universe and caller-supplied group memberships.
The supplied historical sector/industry identities are validated against the original cutoff.
A later classification cannot replace the pinned historical group; a newly late group is rejected.
This supports historical group-neutral ranking integration. A new group-conditioned projection or
within-group redundancy estimator is deferred; the ranking bridge does not claim to fit one.

Held-out raw/residual rank IC uses exact same-origin target/sample intersections when explicitly
requested. TEMPORAL_PANEL's per-time descriptive slices need not cover a complete universe and
must not be interpreted as this mode. No portfolio, risk budget, position sizing, execution,
automatic signal pruning or profitability claim follows from ranks/IC.

See [AFRE-9 ranking](cross-sectional-ranking.md), [construction](orthogonal-signal-construction.md)
and [matched predictive diagnostics](incremental-signal-value.md).

Cross-sectional fitting, evaluation and ranking require one full universe/origin context per
timestamp. Distinct
universe, cutoff, session or build contexts at the same timestamp are rejected rather than pooled
into a single rank-IC slice.
