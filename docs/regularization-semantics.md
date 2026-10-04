# Fixed regularization and convergence semantics

Every penalty is supplied in BaselineModelSpec; changing it creates a new identity.
AFRE-5 never searches penalties or chooses them from validation/test scores.

For equal row weights the objective is exactly:

`sum_i (y_i - intercept - x_i·beta)^2 + l1_penalty*sum_j |beta_j| + l2_penalty*sum_j beta_j^2`.

There is no mean-loss, 1/n or 1/(2n) scaling. Ridge has L1=0; lasso has L2=0;
elastic net supplies both directly. If regularize_intercept is true, the intercept
enters both supplied penalty sums; otherwise it enters neither. NONE intercept
cannot be penalized. No hidden internal feature scaling occurs.

Coordinate descent cycles through intercept then exact feature order, starting at
zero. For a penalized coordinate the update soft-thresholds partial correlation by
L1/2 and divides by squared column norm + L2. An unpenalized intercept uses its
ordinary least-squares update. A zero-norm unpenalized feature takes zero explicitly.
Residuals are recomputed in fixed order after every complete pass.

Convergence requires both maximum coefficient change <= tolerance ×
(1 + maximum absolute coefficient) and maximum KKT violation <= tolerance ×
(1 + maximum absolute 2 Xᵀy). KKT signs include 2 L2 beta and the exact L1 subgradient.
Only TRAIN defines these scales and stopping decisions. Max iterations, tolerance,
final pass count, convergence state and residual are identity-bearing diagnostics.

Nonconvergence FAIL rejects the fit. RETURN_NONCONVERGED persists an explicitly
nonconverged diagnostic artifact; it cannot issue forecasts. Neither policy silently
pretends successful optimization. Tests include exact orthogonal-feature shrinkage,
sparsity, negative coefficients, zero columns and an intentionally tiny iteration cap.
