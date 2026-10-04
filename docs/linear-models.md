# Linear models and numerical diagnostics

OLS solves the supplied rectangular design with deterministic column-pivoted
Householder QR. Pivots choose the largest remaining column norm, breaking ties by
original column order. Householder signs avoid cancellation; back substitution and
inverse permutation recover coefficients. No explicit matrix inverse or normal
equations are used. The intercept is an explicit leading column only under GLOBAL.

The rank threshold is tolerance × maximum original column norm. A short,
rank-deficient, zero-column or insufficiently conditioned system fails; OLS never
silently regularizes or drops a feature. FAIL and RIDGE_REQUIRED both refuse an
unstable OLS fit; the latter records the requested remedy in the spec. A caller must
submit a separate ridge spec. QR diagnostics report rank and max/min absolute R
diagonal as a **condition proxy**, not an exact condition number. A fixed explicit
condition_limit rejects excessive proxy values.

Ridge solves an augmented QR system with sqrt(lambda) diagonal rows for penalized
coefficients and zero extra responses. This regularizes constant or collinear
feature directions when lambda > 0. The intercept remains unpenalized unless
explicitly configured. Lambda zero follows OLS, including its rank/conditioning
failures. See [exact objective conventions](regularization-semantics.md).

FitDiagnostics retains sample/feature count, TRAIN target mean/population standard
deviation, residual SSE, coefficient L2 norm, column scales, QR rank/proxy when
calculated, iterations, convergence and KKT residual. Coordinate descent does not
claim to have computed QR rank/condition. Constant columns are diagnosed by their
norm/rank behavior; penalized zero columns have the explicit zero coefficient.

Arithmetic order follows canonical row and feature order. Stable norms and
math.fsum accumulation reduce unnecessary error; all outputs are checked finite.
Large magnitude or overflow fails explicitly. Numerical fixtures recover known
intercepts/coefficients, singularity, fixed ridge coefficients and regularization
stationarity. They support finite-precision accuracy, not exact real arithmetic or
universal conditioning guarantees.

The stdlib solver has an explicit declared feature ceiling of 128, default 64;
sample, coefficient, dense-cell and iteration bounds constrain work before solving.
The indexed research boundary remains distinct from dense numerical O(n p²) QR.
