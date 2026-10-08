# Turnover diagnostics

The exact convention is `sum(abs(exposure_t − exposure_previous))` over the supplied
per-security path, with an explicit initial policy and no implicit terminal liquidation.
For zero→+1→−1→0, deltas are 1, −2, 1 and turnover is 4. Spread/fee side costs follow each absolute
change; held exposure has zero turnover. Initial +1 versus zero changes entry turnover.

Aggregates retain full path turnover plus included-sample turnover. Cost/truth exclusions and
PIT cohort slicing do not recompute the path or reset initial positions. Cohort turnover is
sum(weight × abs(original full-path delta)) over admitted members; soft weights and effective
support are explicit. Costs/turnover is null for zero turnover. Distinct securities are never
netted to infer an executable trade. Reference notional is a conversion assumption, not a
portfolio sizing rule.

Intensity sensitivity scales declared transitions for cost diagnostics while holding gross
fixed, preserving flat per-trade fee semantics. It does not represent a newly realized
exposure/return path or optimize thresholds. See [exposure rules](research-exposure-rules.md)
and [sensitivity](cost-sensitivity.md).
