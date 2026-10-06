# Partial correlation

`PartialCorrelation` compares two supplied residual sets. Each candidate is separately regressed
on the same supplied references using complete admitted TRAIN observations. Controls, fold, target,
horizon, mode, intercept, preprocessing and fit cutoff must match. Held-out application uses each
frozen projection. Exact sample/full-origin intersections and nonmissing residuals are required.

Pearson correlation of these frozen held-out linear residuals measures conditional linear
association under the declared TRAIN transform. The separate residual-rank statistic is Spearman
of those linear residuals. It is not the classical procedure of rank-transforming every variable
before residualization, and it is not a nonlinear conditional-independence test.

For candidate-versus-target diagnostics, a supplied `PredictiveModelPair` provides a TRAIN-fitted
reference-only target readout. Evaluation subtracts its frozen prediction from later known target
truth, then correlates that target residual with the candidate's frozen projection residual.
Raw and residual target IC/rank IC use the exact same target/sample intersection.

No inverse-correlation shortcut is used. Rank deficiency or failed condition policy fails explicitly;
no hidden pseudo-inverse, held-out nuisance fit, imputation, significance claim or signal selection
is added. Target truth is allowed only in explicit TRAIN target fitting and separate later evaluation;
constructing the candidate residual itself remains target-free.

Orthogonal != independent. Residual association can persist out of sample when TRAIN linear
relationships change. See [construction](orthogonal-signal-construction.md) and
[matched predictive comparison](incremental-signal-value.md).
