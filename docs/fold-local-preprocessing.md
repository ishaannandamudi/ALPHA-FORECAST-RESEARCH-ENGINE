# Fold-local preprocessing

AFRE-4 fits only simple numeric preprocessing using AFRE-1 NormalizationSpec and
NormalizationState. FoldPreprocessingSpec records method/version, zero-scale policy
and explicit winsor quantiles. FoldPreprocessingState binds that state to the exact
dataset/fold and exact admitted research sample IDs, plus skipped missing observations.
PreprocessingScope distinguishes TRAIN_PARTITION from prepared WITHIN_ORIGIN
and WITHIN_ORIGIN_GROUP contracts; group scope names issuer/sector/market. Fitting
the prepared within-origin scopes fails explicitly in AFRE-4.
Only TRAIN samples with labels known by fit cutoff can contribute; validation and
sealed TEST never determine parameters.

| Method | TRAIN parameters |
| --- | --- |
| NONE | No learned parameters |
| STANDARDIZE | Arithmetic mean and population standard deviation |
| ROBUST_STANDARDIZE | Median and linearly interpolated Q75 − Q25 |
| MINMAX | Minimum and maximum − minimum |
| WINSORIZE | Linearly interpolated lower/upper quantiles, default 0.05/0.95 |

Zero standard deviation/IQR/range fails by default. Explicit UNIT_SCALE substitutes
one and is included in identity. Empty/nonfinite/nonnumeric fitting fails. Missing
features stay missing and their representative sample IDs appear in skipped_sample_ids.
No imputer, rank fit, feature selector, factor estimator or predictive model is implemented.

Each origin/security contributes one feature observation regardless of how many
TRAIN target horizons that origin supplies. The smallest canonical sample identity
selects a deterministic representative. Repeated use of the same vintage at different
origins retains origin-level weights in the research wrapper, while the AFRE-1 state
pins the unique exact feature-vintage IDs. Statistics accumulate in sorted origin/security
order; insertion order and Python hash seeds do not affect output.

The state uses fit_cutoff_ns = fold.training_cutoff_ns and available_ns >= that cutoff.
`apply_state` and prepared export require an explicit application time >= available_ns.
Prepared export additionally rejects application before each raw input availability.
Retrospective TRAIN transformation occurs at the fold fit time. It does not backdate
normalization into the raw historical feature, change the AFRE-1 vintage, or assert that
learned statistics were usable at each earlier origin. Recomputing all parameters from
the pinned TRAIN set is part of contamination audit. A different availability time
creates a distinct immutable fit state.
