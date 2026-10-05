# Cross-horizon dependence

DependenceMethod is NONE or EMPIRICAL_RESIDUAL_COVARIANCE. There is no implicit
joint predictive distribution, copula, covariance scaling or correlation matrix.
Empirical covariance describes historical residual dependence, not a causal link.

Residuals are truth minus the exact horizon-specific AFRE-5 point model prediction,
or the explicit shared-backbone prediction. They are retrospective TRAIN residuals,
not held-out or cross-fitted residual estimates. Existing immutable TRAIN matrices
already encode AFRE-4 membership, purge/embargo and each horizon's label cutoff.
Alignment uses the full ForecastOrigin identity, including stable security,
knowledge cutoff, universe, session and build context. Only the intersection of
required horizons whose completed verified truth is known at dependence cutoff
contributes. No VALIDATION/TEST label or unmatched row may fit covariance.

CovarianceArtifact declares GLOBAL_SHARED ownership and pins fit run, ordered
horizons, matched sample/target IDs,
residuals, per-column means, matrix, centering version, explicit population N or
sample N−1 denominator, cutoff, availability and numerical tolerance. Sample
covariance needs two observations. Corrections inserted later cannot replace
frozen rows. Publishing or auditing replays the exact matrix from those inputs.

Symmetry, nonnegative diagonal and a deterministic bounded unpivoted Cholesky-like
PSD check run before publication. Tolerance is explicit, positive and at most1e−6;
checks use tolerance×max(1,max absolute entry). Small residual pivots are treated as
zero for validation and their remaining column must also be within tolerance.
The matrix is never repaired or changed. Near singular or strongly rescaled
matrices may reject conservatively; this is bounded validation, not an eigenvalue
solver or a guarantee of high precision under arbitrary conditioning.

Zero variances are allowed for covariance. Correlation is deliberately not exposed;
there is no division by zero or fabricated correlation for a degenerate horizon.
Covariance state must be available by forecast-origin cutoff to attach to a causal
bundle. It does not turn separate marginal forecasts into a full joint density.
