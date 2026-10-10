# Exact probabilistic fusion

FIXED_PROBABILITY_MIXTURE combines exact compatible AFRE-6 laws and AFRE-12 finite mixtures with nonnegative simplex weights. Nested laws flatten into explicit component records preserving source/output IDs and exact component parameters. Component and empirical-atom bounds apply before publication. Zero-weight components are omitted mathematically; source provenance remains explicit.

A Gaussian mixture remains a Gaussian mixture. It is never collapsed to one Gaussian. Empirical source laws retain weighted finite components/atoms. Quantile-only sources are INCOMPATIBLE with full-law fusion: source quantiles are never averaged into a fake distribution or CDF.

The exact finite law provides weighted CDF and strict `P(Y > x)`, finite expectation and within-plus-between variance. Empirical ties use the native strict exceedance convention. Finite Gaussian mixtures use exact log-sum-exp density/NLL. Native analytic Gaussian/empirical pair primitives provide CRPS. Empirical density/NLL is unavailable. Mixture quantiles are explicitly unsupported. No cross-source or cross-horizon joint law is invented.

Probability contributions are mixture weights attached to exact component laws, not additive realized returns. Calibration state stays in source provenance. Fusion does not refit calibration or claim that a mixture is calibrated because a contributor was calibrated. No automatic mixture calibration bridge exists.

Independent Gaussian/empirical fixtures verify mean, variance, threshold, CDF, NLL and CRPS; the demo reports maximum numerical errors. [Missingness](fusion-missingness.md) determines effective simplex weights per sample.
