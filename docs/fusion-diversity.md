# Diversity is separate from quality

DiversityMatrix operates on one exact common sample-ID intersection across the declared compatible source columns. It rejects duplicate sample/source cells and mixed target/horizon/kind/unit semantics. Missing rows are explicitly excluded. Canonical IDs determine order, never vector position. Pearson and Spearman correlation retain the native insufficient/constant-vector states and average-rank tie convention.

Each pair reports prediction correlation, rank correlation, mean absolute prediction disagreement and sign agreement. These are different quantities. Later error correlation requires an explicit truth cutoff and exact pinned TargetVintage evidence. Prediction diversity is target-free. TEST error diversity outside the sealed evaluation protocol is unsupported. Diversity does not tune weights or establish improvement.

Weight dominance uses normalized absolute magnitudes. For nonnegative simplex weights, effective source count is `1/sum(w*w)` and entropy is `-sum(w*log(w))`. Signed/unconstrained rules do not receive simplex interpretations. WeightStability compares compatible explicitly supplied frozen fits and reports ranges/sign stability/concentration. It selects no weights and implements no rolling health automation.

Independent vector fixtures check Pearson, Spearman, disagreements and sign agreement. Forecast quality is assessed separately by [fused versus component evaluation](fusion-evaluation.md).
