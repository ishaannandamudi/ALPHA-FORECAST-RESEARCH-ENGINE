# Proper probabilistic scoring rules

Scores use exact admitted truth pairs and explicit proper-scores-v1 conventions.
Unsupported scores remain typed UNSUPPORTED with no numeric value; unavailable
truth produces exclusions and INSUFFICIENT_OBSERVATIONS when no pairs remain.
COUNT is zero for an empty paired set. Scores do not mutate models or forecasts.

Gaussian negative log likelihood is log(sigma)+log(2*pi)/2+(y-mu)²/(2*sigma²).
Density is evaluated in log space for NLL, avoiding underflow from taking log of a
numerical PDF. Finite negative NLL is valid for continuous densities above one.
Empirical and quantile-only forecasts have no continuous NLL; atoms are not silently
assigned densities. Unrepresentable finite arithmetic fails explicitly.

Gaussian CRPS uses sigma*[z*(2*Phi(z)-1)+2*phi(z)-1/sqrt(pi)], z=(y-mu)/sigma.
Implementation uses (y-mu)*erf(z/sqrt(2)) to avoid multiplying sigma by an overflowing
standardized z. Exact empirical CRPS is E|X-y| - E|X-X'|/2 over the n equal-mass atoms.
The deterministic sorted implementation integrates step-quantile pinball terms in
O(n); it is empirical-distribution CRPS, not an unbiased fair-ensemble estimator.
QUANTILE_SET CRPS is unsupported: sparse quantiles define no complete distribution.
The [scoringrules empirical CRPS reference](https://scoringrules.readthedocs.io/en/latest/generated/scoringrules.crps_ensemble.html)
provides the expectation definition; the
[Gneiting–Raftery paper](https://doi.org/10.1198/016214506000001437) discusses proper scores.

Pinball(q,a,y) is q*(y-a) when y>=a and (q-1)*(y-a) otherwise. Brier(p,event) is
(p-I(event))². Mean pinball/Brier gives equal weight to the exact requested level/event
sets; different definitions cannot be silently compared. Sample aggregation gives
equal weight to used pairs, preserving sample counts and per-level/event scores.
Lower candidate-minus-reference proper-score deltas are descriptively better.

Coverage, interval width, quantile frequency, sharpness scale and PIT are diagnostics,
not individually proper scoring rules. Scale is chosen sigma for Gaussian and
empirical TRAIN spread for the other families. No fitted probability, quantile or
interval correction follows from diagnostics. AFRE-7 owns calibration transformations.

Offline numerical evidence includes normal CDF/inverse tabulations, NLL at N(0,1),
CRPS=.23369497725510913 at N(0,1),y=0, CRPS=.10339992515976162 at N(.1,.4²),y=0,
independent CDF-integral Simpson quadrature, empirical pairwise CRPS, exact Type-7
quantiles and threshold atoms. The [profile](../benchmarks/probabilistic.py) reports
absolute errors and tail behavior without adding runtime dependencies.
