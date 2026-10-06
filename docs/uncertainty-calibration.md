# Uncertainty calibration and sharpness

AFRE-15 extracts prediction intervals and assesses their coverage; it fits no calibrator or uncertainty penalty. AFRE-7 semantics remain unchanged. A calibrated forecast's exact stored interval can be used only at its stored nominal levels. Identity calibration may preserve the full raw law; marginal calibration does not identify variance or a new full distribution.

Gaussian intervals use the existing declared AFRE-6 approximate quantile implementation; empirical intervals use native Type7 quantiles; sparse quantile sets require both exact supplied levels. Unsupported intervals carry unavailable status and no endpoints/width. Full finite mixtures support moments and proper scores, but quantiles are unsupported. Interval width is exactly upper−lower. Nominal coverage is upper level−lower level and coverage includes endpoints.

Coverage, signed coverage error, width/sharpness, predictive variance and counts are reported separately. Coverage error is empirical−nominal. Narrow intervals are not evidence of accurate calibration or identified uncertainty sources. No opaque combined calibration/sharpness score is emitted. VALIDATION and sealed TEST assessment join later exact known target vintages; they do not refit TRAIN covariance or tune intervals.

Predictive uncertainty does not establish trading profitability. These are descriptive forecast artifacts; portfolio construction, risk optimization and execution remain downstream projects after AFRE. AFRE-15 has no direct external-engine dependency.
