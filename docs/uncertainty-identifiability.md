# Uncertainty identifiability

Every component carries one of `IDENTIFIED`, `PARTIALLY_IDENTIFIED`, `PROXY_ONLY`, `UNIDENTIFIABLE`, `INSUFFICIENT_DATA`, `UNAVAILABLE`, `INCOMPATIBLE`. Only the first three may carry a numerical value. Nonnegative finite numbers are mandatory. Status is evidence-specific; the same category can be unsupported for a different source or measure.

| Evidence | Claim | Status |
| --- | --- | --- |
| Full Gaussian or empirical law | Total predictive moment | IDENTIFIED |
| Full finite mixture | Within/between mathematical variance terms | IDENTIFIED |
| Fixed full-rank OLS and declared iid correct-model assumptions | Noise estimate and readout covariance | PARTIALLY_IDENTIFIED |
| Declared distinct matched models | Equal-weight prediction spread | PROXY_ONLY |
| Point expert outputs | Weighted spread/pairwise absolute disagreement | PROXY_ONLY |
| Supplied regime membership | Discrete state entropy in nats | IDENTIFIED |
| Supplied regime state fitted means | Weighted state-mean ambiguity | PROXY_ONLY |
| Event-conditioned/base difference | Absolute prediction shift | PROXY_ONLY |
| Quality flags without numerical mapping | Retained states, no penalty number | UNAVAILABLE |
| Total law alone | Causal aleatoric/epistemic split | UNIDENTIFIABLE |
| Sparse quantile marginals | Predictive variance | UNAVAILABLE |
| Ridge/tree covariance or incompatible units | Requested estimator | INCOMPATIBLE |
| Too few TRAIN residual degrees/support | Requested estimate | INSUFFICIENT_DATA |

Measures are variance, standard deviation, interval width, entropy, disagreement, score variance and quality penalty. Entropy uses nats; quality scores use diagnostic units; variance/score variance use squared exact target units; standard deviation/width/disagreement use target units. `SCORE_VARIANCE` denotes supplied matched model prediction-score spread here, not variance of proper losses. No percentage attribution, Hessian surrogate, arbitrary residual share or numeric quality penalty is invented.

Predictive uncertainty does not establish trading profitability. These are descriptive forecast artifacts; portfolio construction, risk optimization and execution remain downstream projects after AFRE. AFRE-15 has no direct external-engine dependency.
