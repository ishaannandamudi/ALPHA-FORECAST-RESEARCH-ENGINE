# Bounded temporal model families

`EXPONENTIAL_DECAY_LINEAR` forms feature j's aggregate as `sum(exp(-lambda * age_seconds) * standardized_value)` over unmasked observations, then predicts `intercept + dot(readout, aggregates)`. Weights are unnormalized; lambda is supplied, finite and nonnegative. At lambda=0 this is the sum, not the mean. Timestamp-union truncation and masks are explicit in the window.

`LINEAR_STATE_SPACE` uses one independent state per feature, zero initial state and supplied stable diagonal transition `-1 < a < 1` with positive gain b. For each unmasked token: `h_j = a*h_j + b*x_j`. A masked feature skips its update; padding has no influence. The final state has weights `b*a**remaining_unmasked_tokens`, independently verified against recurrence. Negative a is allowed and declared. This is an observation-step linear state system; it does not assume equal elapsed time or learn transition parameters.

Both learn only a bounded linear readout through AFRE-5 pivoted Householder QR. Fixed positive ridge uses augmented rows with an unpenalized intercept; zero ridge is permitted if rank/condition policy succeeds. Fit artifacts retain exact TRAIN/dataset/transform/spec IDs, coefficients, loss, rank, condition proxy, seed and actual fit clocks. Optimization is one direct solve, with no iterative search or automatic model selection.

Contributions pin source observation, standardized token, temporal weight, readout coefficient and exact product. Their sum plus intercept reconstructs output. State trajectories are retained. Coefficient ranges across compatible supplied fits are descriptive; diagnostics are not causal importance and never prune/refit. Readout penalties may differ in this explicitly descriptive sensitivity comparison; dynamics/feature/window/target/preprocessing must agree.

SIMPLE_RECURRENT, tanh recurrence, CAUSAL_ATTENTION_POOL, learned attention, bidirectional models and deep networks are unsupported and not advertised. Maximum history128, features/state16, TRAIN rows2000, work cells2,000,000; finite arithmetic fails closed on overflow. [Profile](sequence-benchmark.md).
