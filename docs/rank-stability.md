# Rank stability

RankStability compares two explicitly supplied, temporally ordered compatible origins.
They must pin the same target/horizon, model/provider/statistic, eligibility policy,
universe definition, direction, ties, normalization, group taxonomy and missingness
rules. The caller chooses the pair; AFRE does not infer that no intermediate ranking
exists. Calendar/session semantics remain those of the same universe definition.

SAME_MEMBERS requires both eligible and ranked security sets to match. INTERSECTION
permits changes and reports ranked intersection/additions/removals plus eligible
additions/removals and a separate same_eligible_members flag. Changes caused by missing
scores are distinguishable from changes in constituents.

Spearman uses ranks recomputed on the exact ranked-security intersection with the
declared tie convention. N is reported; degenerate intersections remain undefined.
Mean rank displacement uses absolute changes in the original full-cross-section
ranks for intersecting members, so it also reflects changes in peer composition.

Top-K overlap uses each original full ranked set, with stable-ID tie splitting.
It reports overlap count and count/K only when both sets contain K members. Ranked
membership turnover is symmetric-difference/union of ranked sets; eligible membership
turnover uses the corresponding eligible sets separately. Empty union is explicitly
zero. These are descriptive membership/rank diagnostics, not portfolio turnover,
transaction-cost estimates or trading rules.

Separate AFRE-8 horizons must have separate stability series. There is no cross-horizon
score fusion. Restart, reverse insertion and four hash-seed regressions compare the
entire semantic ranking/evaluation/stability bytes.
