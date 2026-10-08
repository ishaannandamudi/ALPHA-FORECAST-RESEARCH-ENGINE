# Forecast degradation

`StabilityComparison` pins both metric/spec IDs, environment pair, exact score/intersection policy, comparability, delta, optional relative delta and availability. Absolute delta is environment minus the predeclared baseline. Relative delta divides by the baseline magnitude only above the pinned tolerance. A zero baseline does not produce an infinite or misleading percentage.

The optional separate `ForecastDegradation` requires that both source specs named that exact baseline before evaluation. MAE/MSE/RMSE/CRPS/NLL/Brier/pinball/coverage error/ECE/MCE have higher-is-worse orientation; R²/IC/correlation/sign accuracy have lower-is-worse orientation. Coverage itself, width and prediction mean are descriptive, with no automatic health classification.

Metric target, actual horizon, exact fold, producer/calibration identity, score levels/threshold/bins, minimum count, weighting, sample mode and truth cutoff must agree. Explicit cross-model comparison is descriptive and cannot choose a winner. Native different cohorts remain partially comparable; common/pairwise results must carry identical sample and truth IDs. Unsupported/insufficient metrics propagate their state and reason. No universal stability score, automatic refit/pruning/promotion or profitability assertion exists.
