# Cross-sectional normalization

Origin-local normalization uses contemporaneous predictor values already available
at the exact ranking origin. This is distinct from AFRE-4/5 learned historical
preprocessing, whose fitted state must use TRAIN only. It never uses realized
application-time targets, future peers or today's universe projected backward.

NormalizationPolicy pins NONE, ZSCORE, MEDIAN_MAD or PERCENTILE, minimum count,
denominator, MAD multiplier and fixed zero-scale/percentile conventions. PeerState
pins the exact RawScore IDs, transformed values, location/scale, quality and clock.
All reductions use canonical stable-security order and bounded finite arithmetic.
Overflow rejects rather than clipping values.

ZSCORE subtracts the mean and divides by the explicitly supplied population N or
sample N-1 standard deviation. MEDIAN_MAD subtracts the ordinary median and divides
by `median(abs(x-median(x))) * mad_scale`. Default mad_scale=1; Gaussian consistency
scaling is not implicit. Even-N medians average the two central values. Zero standard
deviation or zero MAD produces explicit CONSTANT quality and zero transformed
scores under the sole supported `explicit-zero` rule. A nonconstant vector can have
zero MAD; this is still recorded as scale degeneracy, not an ordinary valid transform.

PERCENTILE uses the ranking's exact direction and tie policy. Since larger percentiles
already mean better, ranking the percentile layer always uses HIGHER_BETTER; it does
not reverse LOWER_BETTER twice. Dense ranks deliberately retain the declared N-based
denominator. No winsorization, clipping, imputation or learned score scaling exists.

TOO_SMALL, CONSTANT, UNAVAILABLE and EXCESSIVE_MISSINGNESS are typed states. Below
minimum count or beyond the supplied missing-fraction threshold, entries stay
auditable but no ranks are issued. Constant scores can retain tied ranks while the
quality and undefined IC stay explicit. Thresholding is a supplied admission rule,
not automatic model selection. Raw and normalized values remain separate.

The optional relative linear model reuses a completed AFRE-5 CROSS_SECTIONAL_LINEAR
model's exact admitted TRAIN matrix and existing QR/individual squared-error loss.
It groups rows by all ForecastOrigin information fields except security. Optional
WITHIN_ORIGIN target demeaning uses only realized TRAIN responses known by cutoff,
with the exact groups and means retained. It predicts relative outcomes using fixed
coefficients and a feature-only causal scaffold. It never subtracts unknown current
realized target means. The base target/benchmark and preprocessing remain pinned;
the centered response semantics are explicit in CrossSectionModelSpec. There is no
learning-to-rank, learned risk aversion, model selection or uncertainty model for
these centered outputs.
