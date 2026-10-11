# Exact common challenger matching

The evaluator constructs one `CommonMatchedEvidence` for all declared participants. Each matched sample must have exactly one supplied shadow per participant, one explicit truth vintage, the same native origin/security, target/horizon/unit, dataset/fold and declared window. Research samples retain PIT eligibility. Duplicate shadow revisions per participant/sample are rejected; callers must choose exact revisions.

Only common samples with completed, verified truth known at the frozen cutoff survive. Missing participant rows, absent explicit truth assignments, outside-window/cohort samples and late truth have named exclusions. Target, horizon, unit or fold/dataset mismatches produce INCOMPARABLE, rather than misleading small-N scores.

Every participant metric retains identical common sample/truth IDs and count. Unsupported metrics stay unavailable on that same support. MAE/MSE/RMSE/R²/Pearson/Spearman/sign accuracy use native score conventions. Undefined constant-target/prediction statistics are unavailable. Target-valued errors and probability scores require exact target units.

IC/rank IC, mean rank displacement and top-K overlap operate within exact same-origin cross-sections. Requests pin minimum cross-section size and K. Native average-rank ties are used for displacement and rank correlation; top-K ties are deterministic by stable security ID. An undersized or undefined origin makes the requested ranking result unavailable, without silently changing support.

Optional hard native AFRE-17 event, regime, sector, universe and custom environments scope the common support identically. Exact memberships and their origin evidence are retained. Soft weighted cohort promotion comparisons are explicitly INCOMPARABLE. The optional uncertainty context is retained separately, not turned into a universal penalty. Orthogonal signals can participate where native target/horizon/unit semantics are compatible; point-error metrics do not invent target units for residual signals.
