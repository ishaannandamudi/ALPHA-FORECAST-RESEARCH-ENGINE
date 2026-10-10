# Nonlinear feature interactions

AFRE-13 is complete: engine0.14.0, nonlinear schema1.0, shared store1.13/user14.
AFRE-0 through AFRE-25 remains the frozen 26-phase roadmap. Earlier public schemas
and source/test semantics are unchanged. Stop after AFRE-21; AFRE-17 Invariance & Stability Research is complete. AFRE-18 cost-aware research evaluation is complete.

The package separates immutable semantic definitions, exact origin-specific scalar
inputs, pure transforms, TRAIN matrices/fitted state, linear/tree fitting, target-free
forecasts, later matched evaluation, descriptive stability and bounded unified audit.
No automatic interaction generation or feature selection is exposed. The caller supplies
specifications before fitting. TEST cannot choose interactions, knots or splits.

Every native ordinary feature must be an exact AFRE-4 selected vintage. Neutral extra
predictors enter an explicit scalar grid attached to those admitted samples; AFRE-4
labels and partition membership remain pinned. A model requires the complete admitted
TRAIN sample set for its exact target. Partial TRAIN selection is unsupported.

Input semantic versions and ordered exact source revisions are identity-bearing.
A correction creates new scalar/interaction/forecast identity; old bytes replay.
Physical computation clocks do not backdate: TRAIN-derived matrix values computed at
fit time are fit data, not historically deployed features. Forecast computation must
occur at the origin cutoff, subject to every input, state and model availability.

Prediction/application never reads TargetVintage or TRAIN matrices/responses. Fits,
predictions and evaluations freeze repository reads before atomic publication. Audit
replays source bindings, knot fitting, matrices, coefficients, trees, forecasts,
evaluations and stability with explicit node/depth/byte bounds.

Safe canonical JSON only. No runtime network, executable payload, provider-selected
path, external engine import or heavy ML dependency. Zero runtime dependencies.
See [definitions](interaction-definitions.md), [transforms](nonlinear-transforms.md),
[trees](shallow-tree-models.md), [evaluation](nonlinear-evaluation.md) and
[report](AFRE_13_COMPLETION_REPORT.md).


## AFRE-14 sequence integration

Causal interaction outputs may become ordered sequence inputs with exact definitions, units, source clocks and nested expert-horizon/attestor checks.
See [temporal sequences](temporal-sequence-models.md) and [causal sequence training](causal-sequence-training.md).
AFRE-15 uncertainty decomposition is complete; AFRE-16 Signal Orthogonalization & Redundancy Analysis is complete; AFRE-17 Invariance & Stability Research is complete; predictive metrics do not establish profitability.

## AFRE-15 uncertainty integration

AFRE-15 supports declared fixed-design unpenalized linear-readout covariance, conditional on supplied transforms/interactions. Tree and ridge epistemic covariance remains unsupported. See [uncertainty decomposition](forecast-uncertainty-decomposition.md).

Predictive uncertainty does not establish trading profitability. These are descriptive forecast artifacts; portfolio construction, risk optimization and execution remain downstream projects after AFRE. AFRE-15 has no direct external-engine dependency.

## AFRE-16 integration

Nonlinear outputs or causal scalar inputs can enter supplied TRAIN projection analysis with exact model/definition identity. Linear residualization does not remove arbitrary nonlinear dependence or prove unique economic information. No interaction search or source/model replacement occurs.

See [signal orthogonalization](signal-orthogonalization.md). Supplied candidate/reference sets are fixed;
no automatic pruning or broad signal search occurs. Orthogonal != independent, residuals are not
guaranteed alpha, and predictive metrics do not establish trading profitability. The frozen roadmap
remains26 distinct phases, AFRE-0 through AFRE-25; AFRE-17 Invariance & Stability Research is complete.

AFRE-17 adds [declared environment stability research](invariance-stability-research.md) over frozen artifacts. PIT memberships, target/horizon compatibility, exact intersections and minimum counts remain explicit. Input shift and error degradation are separate; there is no causal-proof, significance, profitability, auto-refit/prune or promotion claim. AFRE-18 [cost-aware research evaluation](transaction-cost-aware-research.md) is complete.
