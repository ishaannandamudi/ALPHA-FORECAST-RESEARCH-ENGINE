# Signal redundancy definitions

Redundancy depends on the metric. Pearson correlation measures matched linear association;
Spearman uses deterministic average ranks for ties. Neither correlation nor absolute correlation
is a percentage of redundant information. Orthogonality does not establish independence.

A `RedundancyMatrix` pins supplied signal ordering (candidate, then canonical references), exact
row IDs, partition and one common complete-case intersection for every cell. Missing rows are
explicitly listed as excluded. Every `PointMetric` records N and its defined/degenerate state.
Constant/small-N correlations retain explicit unavailable states. `absolute_pearson` preserves
those states and provides magnitudes without redefining the statistic. TRAIN and held-out matrices
are separate artifacts; no pair independently changes its sample intersection.

The projection reports TRAIN in-sample centered R² through the existing AFRE-5 metric convention,
including for a declared no-intercept model. Held-out R² and MSE evaluate frozen projected candidate
against the raw candidate on exactly the residual's complete sample intersection. A no-intercept
fit does not switch R² to an uncentered convention.

Variance uses the population denominator N and subtraction of each vector's own mean.
`residual_variance_ratio = Var(residual)/Var(candidate)` is undefined for zero candidate variance
or an empty intersection. `variance_redundancy_fraction = 1 - residual_variance_ratio` is explicitly
named, may be negative, and is not silently substituted for R². Bias contributes to prediction MSE
and R², whereas centered variance removes the residual mean; the two summaries can disagree.

Partial association and incremental target-model metrics answer further distinct questions.
No scalar combines these diagnostics into a universal redundancy score. No threshold automatically
accepts/rejects a signal. Sample choice, units, horizon, reference set, intercept and preprocessing
remain identity-bearing inputs. See [partial correlation](partial-correlation.md),
[collinearity](collinearity-diagnostics.md) and [fixed model comparisons](incremental-signal-value.md).
Predictive metrics do not establish profitability or statistical significance.
