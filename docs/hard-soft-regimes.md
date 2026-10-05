# Hard and soft regimes

HARD requires exactly one taxonomy state; SOFT requires every ordered taxonomy state
exactly once with finite nonnegative probabilities. The vector remains unchanged.
The declared tolerance is positive and <=1e-10 (default1e-12); reject-unscaled-v1
checks sum≈1 without normalization. Unknown states, reordered/missing/duplicated
entries, NaN/infinity and incompatible taxonomy versions reject.

Hard state weights are exact one-hot vectors. Soft fits use supplied probabilities
as weights, state value=sum(weight*TRAIN residual)/sum(weight), and Kish support
(sum(weight))²/sum(weight²). Minimum positive-weight distinct samples and effective
support are both required. Application shift=sum(probability*state offset). State
counts, IDs and weights remain explicit; no argmax or mass redistribution occurs.

Soft weighted conditioning consumes upstream memberships as ordinary causal data.
It does not learn a gate or train an expert ensemble. AFRE-12 Mixture of Experts is
separate and deferred. Scarce states invoke a declared whole-output fallback.
Evaluation reports hard groups separately from soft weighted diagnostics; mean
probabilities use matched known-truth members, weighted MAE divides by weight sum,
and low confidence means max probability below the fixed spec threshold.
