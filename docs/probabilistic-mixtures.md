# Finite probabilistic mixtures

MixtureDistribution retains each positive-weight original Gaussian or empirical component
with exact expert/binding identities. It does not collapse the law to one Gaussian.
For F_i, component means mu_i and variances v_i:

- F_mix(x) = sum(w_i F_i(x)).
- Exact threshold events use the same GT/GE/LT/LE component comparison, including atom edges.
- mu_mix = sum(w_i mu_i).
- v_mix = sum(w_i [v_i + (mu_i - mu_mix)^2]).

The centered variance expression is numerically more stable than subtracting large second
moments and includes between-component disagreement. No joint law, covariance or expert
independence is asserted. Point output is the mixture expectation when all components define it.
CDF/event values within the declared sum tolerance of0/1 clamp only roundoff at the boundaries;
weights and interior probabilities are not renormalized.

CRPS uses E|X-y| minus half E|X-X'|, with analytic Gaussian and exact empirical pair terms.
Pair work is bounded. Gaussian-only NLL uses stable log-sum-exp of positive component
densities. Empirical/mixed NLL is explicitly unsupported. Proper-score artifacts and
aggregation reuse AFRE-6; matched expert deltas retain identical truth intersections.

Sparse QUANTILE_SET experts have no exact CDF/expectation and cannot contribute to these laws.
All mixture quantile inversion remains unsupported. Never average quantiles and call the
result a mixture quantile. No approximate replacement distribution is silently supplied.

Component calibration is not mixture calibration. Dedicated assessment records
INSUFFICIENT_DATA, UNAVAILABLE or INCOMPATIBLE; SUPPORTED is reserved and rejected until a
mixture calibrator exists. Evidence must be causal non-TRAIN/non-TEST VALIDATION observations,
with known truth and exact gate/set. Component CalibrationState reuse is incompatible.
