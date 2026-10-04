# Quantile forecasts

QuantileDefinition pins unique sorted interior levels, explicit median q=0.5,
LINEAR_N_MINUS_ONE convention and type7-v1 implementation version. Duplicates,
missing median, NaN/infinity, q=0/1 and crossed forecast values fail. Default
resource budget is 64 levels with a hard declared ceiling of 256. Gaussian levels
also satisfy the numerical inverse domain [1e-12,1-1e-12].

For sorted n-value empirical pool x, position h=(n-1)q, i=floor(h), j=min(i+1,n-1):
Q(q)=x[i]+(x[j]-x[i])*(h-i). Conditional forecasts add the point location.
A single atom returns the atom. For (-2,-1,0,1,2), q=.1/.5/.9 yields -1.6/0/1.6.
This Type-7 reporting convention is explicit; interpolated values need not equal
an inverse of the discrete step CDF. Proper empirical CRPS uses the equal-mass atom
CDF, not a hidden continuous distribution through the reported Type-7 quantiles.

Gaussian Q(q)=mu+sigma*NormalDist.inv_cdf(q). QUANTILE_SET stores Type-7 values at
requested levels only: quantile(forecast,q) requires an exactly stored level.
Empirical/Gaussian query APIs can compute other supported levels without modifying
the immutable forecast or fitted definitions. Full forecasts and their parameters
are accepted by the public quantile/CDF/survival/moment query APIs.

Forecast payloads require nondecreasing values at increasing levels. Crossing is
rejected, never silently repaired by sorting values or fitting a mapping. Pinball
loss at each requested level is reported separately; an equally weighted mean over
that exact declared level set is also recorded. Median remains distinct from mean.
Interval diagnostics use only explicitly requested endpoint levels and include
both boundaries. AFRE-6 never fits quantile/interval/conformal calibration.
