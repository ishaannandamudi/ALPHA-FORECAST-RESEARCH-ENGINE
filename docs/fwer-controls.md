# Family-wise error controls

Bonferroni adjusted p is min(1,m p). Holm sorts by (raw p, immutable plan ID) and applies
the running maximum of min(1,(m-rank+1)p). Published order is canonical identity order;
rank retains the arithmetic order. Ties are deterministic and adjusted values monotone.
Failed/missing slots consume the full declared m, internally at p=1.

Both methods control nominal family-wise error under valid marginal p-values without
requiring independence among hypotheses. Independence of observations inside each exact
sign test is a separate explicit sampling assumption. This distinction matters for
shared forecasts, overlapping families, environments and cost scenarios.

An explicit 0<alpha<1 is mandatory. Supported COMPLETE predeclared rows reject exactly
when adjusted p<=alpha; unsupported/interim rows have no rejection decision. A rejection
is not a causal or profitability claim and does not remove adaptive data snooping.
The implementation uses stdlib arithmetic and independent numerical fixtures.

Reference: [R's adjustment definitions and dependence semantics](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html).
See [families](hypothesis-families.md), [FDR](fdr-controls.md) and [controls](multiple-testing-controls.md).
