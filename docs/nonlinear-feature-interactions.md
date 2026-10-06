# Nonlinear feature interactions

AFRE-13 is complete: engine0.14.0, nonlinear schema1.0, shared store1.13/user14.
AFRE-0 through AFRE-25 remains the frozen 26-phase roadmap. Earlier public schemas
and source/test semantics are unchanged. Stop after AFRE-13; AFRE-14 remains deferred.

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
