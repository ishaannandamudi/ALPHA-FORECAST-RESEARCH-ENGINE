# Conformal calibration

CONFORMAL_ABSOLUTE_RESIDUAL is an explicit symmetric split-conformal-style
interval. Calibration scores are `abs(truth - raw_median)`, using only admitted
past calibration observations. NonconformityScore pins score and observation ID;
ConformalScoreSet pins sorted scores, alpha, rank, q_hat, estimator and exact
spec/observation-set IDs. Ties sort by observation identity.

For n scores and `0 < alpha < 1`, compute the one-based finite-sample rank
`k = ceil((n+1)*(1-alpha))`, then `q_hat = sorted_scores[k-1]`.
The pinned `ceil-n-plus-one-decimal-alpha-v1` convention uses the exact decimal
representation of the supplied alpha in this rank calculation. It avoids binary
roundoff at integer ranks. Ordinary quantile interpolation is not used. If k
exceeds n the fit rejects; there is no hidden rank cap or infinite interval.

Application uses `[raw_median - q_hat, raw_median + q_hat]`. Spec pins alpha and
the exact central raw interval levels `(alpha/2, 1-alpha/2)`; both must be requested
raw quantiles. CalibratedForecast stores that exact raw interval and the separate
conformal interval, nominal coverage `1-alpha`, raw forecast ID and conformal
state reference. Raw quantiles are preserved; conformal bounds do not masquerade
as newly calibrated marginal quantiles. Proper pinball scores therefore remain
raw for this method; interval coverage/width use the new bounds.

ROLLING_CONFORMAL uses the same score/rank rule on the last explicitly declared
N resolved eligible observations, ordered by origin/security/sample. Candidate
reservations and origin range are explicit. Truth after cutoff is excluded before
window selection. There is no future centered window, automatic refresh or TEST
fitting. Each deliberate new fit/cutoff/window creates a versioned state.

Nominal finite-sample coverage arguments require assumptions such as exchangeability
and appropriate disjoint calibration/predictive training. Nonstationary financial
time series, serial dependence, selection and regime change can degrade coverage.
AFRE does not claim universal or conditional coverage guarantees. The deterministic
leave-one-out exchangeable fixture verifies rank semantics, not coverage for real
markets. Width/sharpness is tracked separately so wide intervals cannot hide
uninformative forecasting. Asymmetric conformal and other scores are deferred.
