# Multi-horizon consistency

ConsistencyAudit records family/unit compatibility, adjustment compatibility,
ordered nested elapsed windows, exact common origin/security and preserved
within-horizon quantile order. It exposes adjacent expected-outcome differences
only for compatible target family, benchmark, volatility annualization and
adjustment semantics. Unsupported
expectations and incompatible units produce explicit None values.

These diagnostics are descriptive. AFRE does not assert a forecast law across
horizons. In particular, nested simple returns are not additive: even realized
sequential simple returns compound. Log returns can add only over exact
non-overlapping path pieces; overlapping horizon forecasts do not identify those
pieces. Quantiles do not add. Expected five-day return need not equal five times
expected one-day return.

Variance does not scale proportionally to horizon automatically. Dependence,
changing conditional information and nonlinear compounding prevent that inference.
No forecast is clipped, rescaled or repaired to satisfy those naive relations.
Across-horizon quantiles may rise or fall while remaining monotone within each
horizon. The audit retains these explicit limitations in its typed checks.
