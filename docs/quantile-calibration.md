# Quantile calibration

QUANTILE_OFFSET pins each selected interior quantile level, including median,
and the exact estimator `type7-residual-q-v1`. For level q and each admitted
calibration observation, residual is `truth - raw_quantile(q)`. Residuals sort
ascending. The offset is the empirical Type-7 q-quantile: position `(n-1)*q`,
linear interpolation between neighboring order statistics. This is the declared
residual statistic, not a vague bias correction or a conformal rank.

Each immutable QuantileOffset retains level, offset, sorted residual values,
observation IDs and spec/observation-set identities. Applying q=0.10's offset to
q=0.05 rejects. The transformation adds each offset to its own raw level; all
unselected raw levels remain unchanged. No truth is read during application.

All resulting quantiles, including unselected ones, must remain noncrossing.
Crossing is rejected during retrospective fit diagnostics and again during
application to new raw output. The implementation never sorts calibrated values,
reassigns levels or silently repairs a crossing. A rejected application publishes
no partial forecast batch. Future raw spacing can cause a fit that was valid on
calibration data to fail during deployment; this is an explicit limitation.

Quantile diagnostics report `fraction(truth <= forecast_q)`, signed deviation
from nominal q, and absolute deviation. Pinball loss remains a separate proper
score. For declared intervals, endpoint quantiles define raw/offset-calibrated
coverage and width. The method does not imply a calibrated full CDF, density,
expected value or variance. Independent level adjustments cannot establish a
joint distribution without an additional explicit construction.

Only explicit non-TEST reservations can fit offsets, with completed verified
truth available by cutoff and raw forecasts that existed historically. Later
truth corrections require new requests/state identities. Same-fit-sample
frequency improvements are retrospective diagnostics, not out-of-sample claims.
