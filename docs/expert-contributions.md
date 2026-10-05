# Expert contributions and descriptive diagnostics

Point composition uses fsum(weight × exact expert value). Each ExpertContribution pins the
binding, original/effective weights, value, weighted contribution and usable/missing reason.
The final point equals the contribution sum. A contribution is arithmetic, not causal importance.

MixtureEvaluation matches later-known truth to exact sample, security, full origin and rich
target. Each expert comparison uses its own available intersection, and both mixture/expert
metrics and deltas use those same sample/truth IDs. Overall mixture coverage and exclusions
remain explicit. Point metrics reuse AFRE-5; supported proper scores reuse AFRE-6. Fixed/learned,
complete/missing and fallback cohorts are descriptive. TEST evaluation creates explicit seals
and preserves the earlier reuse contract; it never trains or changes the gate.

MixtureDiagnostics reports per-expert mean/median/min/max effective weights, zero frequency,
availability rate, mean signed/absolute contribution and positive-weight frequency.
Effective expert count is1/sum(w_i^2), and entropy is -sum(w_i log w_i)/log(n), with singleton
entropy0. These describe concentration, not independence or causal importance. Exact matched
pair prediction/error Pearson correlations and mean absolute disagreement preserve sample
intersections; constant or insufficient series report undefined correlation.

GateDriftDiagnostic compares known, ordered, disjoint origin windows with the same gate/set.
It reports mean-weight changes, availability changes and matched mixture MAE change, or explicit
insufficient support. It does not refit, select or mutate any gate/expert. Feature-distribution
drift and automatic orthogonalization are deferred. AFRE-16 owns orthogonalization/redundancy.

The AFRE-9 bridge creates an explicit immutable derived mixture score and preserves full
same-origin security/PIT group semantics, exact target/gate and matched TEST truth. A ranking
is research output; forecast weights/ranks never constitute portfolio construction.
