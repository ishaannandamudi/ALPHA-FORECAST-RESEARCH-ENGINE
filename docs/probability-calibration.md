# Probability calibration

Each mapping pins one exact ThresholdRequest: value plus GT/GE/LT/LE comparison.
`Y > 0` and `Y >= 0` differ at atoms. A mapping cannot be reused for another
threshold/comparison, rich target/horizon, raw model/spec or CalibrationSpec.
Multiple selected events fit independent mappings. There is no shared complement
representation and no joint probability consistency or full calibrated CDF claim.
Unselected raw events are preserved as raw marginals.

Binned calibration uses fixed strictly increasing edges from 0 to 1. Bins are
left closed/right open, with the final bin including 1. Parameters pin minimum
count, empirical binary rate and insufficient-bin policy: RAW uses the incoming
probability unchanged; FAIL rejects the fit. Counts, raw mean, observed rate and
source observation IDs are persisted. No edge or minimum is learned from TEST.
An empty bin has no empirical rate; it is never assigned a fabricated zero rate.

Isotonic calibration uses deterministic equal-weight Pool Adjacent Violators.
Pairs sort by probability then observation identity. Identical inputs aggregate
into a tie group with integer successes/count. Adjacent groups pool while the
left rate exceeds the right, comparing integer cross products. Equal rates do
not pool. Blocks persist lower/upper observed input, count (the weight), integer
successes, exact binary rate and sorted source observation IDs. Insert order and
hash seed cannot alter the result.

Within a pooled block the rate is constant. Between the left block's upper input
and right block's lower input, linear interpolation fills the gap. Values below
or above the observed domain CLAMP_EDGE. This pinned rule is monotone and stays
in [0,1]; nonfinite/out-of-domain query probabilities reject. No hidden
extrapolation or smoothing occurs.

Diagnostics use the spec's fixed bins independently for raw and calibrated
probabilities on identical truth samples. Every nonempty bin reports count,
mean predicted probability, empirical binary frequency and absolute gap. Empty
bins have null statistics and zero weight. ECE is
`sum_bin (count / N) * abs(observed_frequency - mean_probability)`;
MCE is the largest nonempty bin's absolute gap. Brier is the separate mean
squared binary error; observed event frequency is reported explicitly.

ECE/MCE depend on binning, can hide within-bin error, and have sample uncertainty.
They are not proper scores and do not establish discrimination or usefulness.
Fit diagnostics reuse calibration truth and are labeled retrospective. Independent
later evaluation is required. A synthetic known-rate Brier improvement test checks
the implementation, not model selection or a profitability claim.
