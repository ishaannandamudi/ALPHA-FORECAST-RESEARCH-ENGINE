# Declared predictive distributions

The closed supported families are EMPIRICAL_RESIDUAL, GAUSSIAN_LOCATION_SCALE and
QUANTILE_SET. Student-t, bootstrap resampling, parametric heavy tails and mixtures
are not implemented or advertised. Distribution state is REGULAR or DEGENERATE.
All parameters, stored values and scores must be finite; overflow fails explicitly.

For conditional residual forecasts, Y = fitted point value + uncertainty pool value.
RAW retains every admitted TRAIN residual. CENTER_MEAN subtracts the exact TRAIN pool
mean, recording raw mean and centering shift; it never uses validation outcomes.
For unconditional TRAIN_TARGETS forecasts, Y is the raw TRAIN target pool and RAW is
mandatory. No feature-specific, security-specific or adaptive scale model is fitted.

EMPIRICAL_RESIDUAL is an equal-mass discrete distribution over every sorted TRAIN
pool value, including duplicates. Location is the point value or zero. Expected
value is location + pool mean; conditional variance is population pool variance.
Atom inequalities remain exact, including equality at a rounded shifted atom.
A constant pool is explicitly DEGENERATE, variance zero, with deterministic atoms
and quantiles. It has no continuous density/NLL; no Gaussian density is invented.

GAUSSIAN_LOCATION_SCALE is continuous N(mu,sigma²): mu is conditional point value
plus fitted pool mean, or the raw TRAIN-target mean for unconditional forecasts.
Sigma follows one fixed declared ScaleSpec: TRAIN_RESIDUAL_STD uses population
sqrt(sum((x-mean)²)/n); TRAIN_RESIDUAL_MAD_SCALED uses median(abs(x-median(x))) times
the explicit positive consistency factor (default 1.482602218505602); FIXED_SCALE
uses the supplied positive scale. Diagnostics always retain empirical population
STD and MAD as well as chosen sigma. Sigma² is the forecast variance.

A zero STD or MAD continuous scale rejects fitting atomically, with no implicit
floor. A caller may independently declare positive FIXED_SCALE; degenerate TRAIN
observations remain visible in diagnostics, while the chosen Gaussian is continuous.
Empirical/quantile models accept descriptive population STD only; scale never
resizes their atoms or supplied quantiles.

QUANTILE_SET stores only declared Type-7 empirical quantiles around conditional
location, or over raw unconditional targets. It imposes no interpolation density,
CDF, survival, event probability, expected value or variance between sparse quantiles.
Those queries/scores explicitly reject or report UNSUPPORTED. Its scale is descriptive
TRAIN pool spread, not an inferred variance of a sparse distribution. All-equal stored
quantiles have a DEGENERATE quantile state, which need not imply all original atoms
are identical; original pool diagnostics retain that distinction.

The bounded approximation version is erfc-normaldist-v1. Normal CDF uses stdlib
math.erfc and normal inverse uses Python 3.11 statistics.NormalDist.inv_cdf. Gaussian
quantile requests are bounded to [1e-12,1-1e-12]. Tails use erfc directly for survival
rather than cancellation-prone subtraction. Numeric underflow may produce exactly
zero tail probability; no clipping/recalibration is applied. This is a declared
Gaussian assumption, not learned tail behavior. See the
[Python NormalDist documentation](https://docs.python.org/3.11/library/statistics.html#normaldist).
