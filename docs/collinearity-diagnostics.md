# Collinearity diagnostics

The projection retains full design rank, a Frobenius condition estimate for the QR triangular
factor, a common-intersection Pearson/Spearman matrix and conventional centered VIF per reference.
The condition estimate is not advertised as a spectral condition number. The declared tolerance
and condition threshold are enforced by both deterministic QR and the triangular-factor calculation.
A floating-point condition estimate a few ulps below 1 is clamped to the mathematical lower bound 1.

For reference j, an auxiliary with-intercept regression on the other references uses the same
complete TRAIN design. `VIF_j = N * population_variance(reference_j) / auxiliary_SSE`, equivalent
to `1/(1-R_j²)` under these conventions. A single varying reference has VIF 1. Constants, unsupported
auxiliary rank/conditioning, or residual SSE at the declared near-perfect tolerance have unavailable
VIF (`None`); no infinite number is invented. VIF uses centered auxiliary regressions even when the
primary projection deliberately has no intercept.

A primary deficient or ill-conditioned projection fails. It does not silently drop a column,
regularize, pseudo-invert, cluster signals or choose a survivor. Pairwise correlation can miss
multivariate redundancy. These diagnostics depend on the declared units, preprocessing, intercept,
TRAIN sample intersection and condition policy. They do not prove independence, significance,
economic novelty or trading profitability.

Independent fixtures compare QR coefficients, residuals and VIF with centered arithmetic and small
Gaussian elimination oracles. See [the tests](../tests/orthogonalization/test_numerics.py),
[the profile](orthogonalization-profile.json) and [redundancy definitions](signal-redundancy.md).
