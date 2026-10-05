# Fixed and learned expert gates

FixedGateSpec pins one ExpertSet, canonical (expert ID, weight) pairs, sum tolerance and
`reject-unscaled-v1`. Weights must be finite, nonnegative and sum to1 within a declared
positive tolerance no larger than1e-12. No silent rescaling occurs. Missing-policy
renormalization is separately declared and preserves original weights.

LearnedGateSpec pins the exact set, AFRE-4 fold/cutoff, gating-feature semantic IDs, minimum
sample count, ridge penalty, iteration ceiling, convergence tolerance, seed, no-intercept
policy, normalization and implementation version. Only LEARNED_LINEAR constant simplex
weights are supported. Softmax/contextual/neural gating and model search remain deferred.
Causal features are audit evidence under `causal-audit-only-no-contextual-weighting-v1`.

GateTrainingRow holds one admitted TRAIN sample, exact binding/feature grid, known target
vintage and response, full origin and spec. Every expert must have been historically usable
at that TRAIN origin. A later native model's fitted predictions are not admissible substitutes.
Labels must be verified, completed and known by the declared fold cutoff. VALIDATION/TEST
rows are rejected. TEST perturbation cannot alter a fit using the same TRAIN evidence.

The deterministic solver minimizes mean squared error plus a fixed ridge penalty over
nonnegative sum-to1 weights. It scales X/y jointly, starts uniformly, uses a fixed Lipschitz
step and Euclidean simplex projection, and reports the projected-gradient mapping residual.
Rows, work cells and iterations are bounded; nonconvergence fails and persists no model.
GateModelArtifact pins exact TRAIN rows, parameters, objective, convergence diagnostics,
fit start/completion and final availability. Published parameters are independently replayed.

GatingFeatureReference supports exact security FeatureVintage, neutral scalar ExternalSignal
and security-scoped filtered RegimeSnapshot state weight. Source quality, security, as-of,
feature identity, scalar and final availability are checked; reconstructed delivery requires
local approved evidence. Current positions, orders, inventory, execution and target truth are
forbidden. Deployment retains the exact same declared feature definitions and origin.

Application requires the gate, features, contributing experts and actual computation available
by origin. Fitted TRAIN samples cannot masquerade as held-out application. No automatic
fallback tuning, expert selection, pruning or refit occurs.

Fixed gates pin explicit `available_ns` (default0 means a declared policy available from
clock epoch0). Application includes this clock in the availability floor; a future fixed
policy cannot be applied at an earlier origin. Callers must declare the actual policy
availability for later configurations; hashes cannot authenticate that declaration.
