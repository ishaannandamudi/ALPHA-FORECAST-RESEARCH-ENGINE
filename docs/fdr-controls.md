# False discovery rate controls

BH sorts by (p, immutable plan ID), then computes the reverse running minimum of
min(1,m p/rank). BY multiplies those factors by H_m=sum(1/j,j=1..m) before the same
reverse minimum. Full m includes failed and missing declared opportunities. Raw and
adjusted values stay separate; effects do not change.

q is an explicit family level. BH inference requires INDEPENDENT or PRDS dependence
attestation. UNKNOWN/ARBITRARY gives UNSUPPORTED with no rejection, even if numerical
adjustments are shown. BY allows arbitrary dependence of valid marginal p-values and
is implemented with deterministic bounded harmonic sums, independently checked.

FDR bounds expected false-discovery proportion under its assumptions; it is not the
probability a particular discovery is false. Neither method repairs invalid raw p-values,
leakage, adaptive family generation or a reused search holdout. OPEN/adaptive reports
remain INTERIM. No significance claim implies causal identification or trading profit.

Reference: [R's BH/BY definitions](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html).
See [FWER](fwer-controls.md) and [overfitting](research-overfitting.md).
