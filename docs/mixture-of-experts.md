# Mixture of Experts — AFRE-12

AFRE-12 composes independently identified forecasts for one exact target and horizon.
Engine0.13.0, mixture schema1.0 and store1.12/SQLite13 are additive to AFRE-11.
The frozen roadmap remains 26 distinct phases, AFRE-0 through AFRE-25.

An ExpertReference pins a producer/model contract. An ExpertForecastBinding pins that
producer's exact forecast at a full ForecastOrigin. ExpertSet supplies a canonical producer
order, rich TargetDefinition, output family, maximum age, missing policy and approved
historical-delivery attestors. MixtureRequest supplies a complete presence/absence grid;
MixtureForecast retains original/effective weights, exact contributions and final availability.

Native statistical, probabilistic, event and regime producers coexist with neutral external
microstructure, context, options and generic specialists. All contributing inputs and the
gate must be available by the origin cutoff. The actual mixture computation must also occur
within the origin cutoff; backdated computation is unsupported. Exact same-time availability
is accepted. Applying a fitted gate reads no target truth or TRAIN matrix.

Fixed gates use declared normalized nonnegative weights. Learned linear gates fit one
predeclared TRAIN mean-squared-error objective on the simplex, with optional fixed ridge.
There is no intercept, architecture search, contextual weight map, softmax or neural gate.
Gating features are exact causal audit evidence and do not change the constant fitted weights.
Neither VALIDATION nor TEST fits, tunes, selects or alters a gate. Native in-sample predictions
cannot substitute for historically admissible TRAIN expert forecasts.

Probability output retains a finite component law. Gaussian and empirical mixtures support
CDFs, threshold events, expectation, total variance and CRPS. Gaussian-only NLL uses stable
log-sum-exp; NLL is unsupported for empirical/mixed laws. Sparse quantile-only inputs lack
an exact expectation/law and cannot contribute; all mixture quantiles are explicitly
unsupported. Quantile averaging is invalid. Component calibration does not calibrate a mixture.

Matched evaluations compare each expert and mixture on identical sample/truth intersections.
Descriptive diagnostics include weights, availability, contributions, effective count, entropy,
prediction/error correlation, disagreement and ordered-window drift. They never refit, prune,
orthogonalize or select experts. Outputs may share information; no independence is assumed.
Expert weight is a forecast-combination weight, never a portfolio weight or trade size.
Predictive performance does not establish trading profitability.

MixtureRepository extends the completed store with immutable JSON and verified projections.
Transactional12→13 migration preserves earlier rows, metadata and DDL. Frozen read snapshots,
exact references, semantic replay, bounded components/rows/work/lineage and append-only
corrections support deterministic replay. Structural hashes do not authenticate a provider
or prove that a dishonest scalar excludes future information.

See [contracts](expert-contracts.md), [gating](expert-gating.md),
[missingness](expert-missingness.md), [probabilities](probabilistic-mixtures.md),
[diagnostics](expert-contributions.md), [external integration](external-expert-integration.md)
and [profile](mixture-benchmark.md). Run the offline demonstration with
`PYTHONPATH=src:. .venv311/bin/python -m examples.mixture_demo`.

AFRE-13 — Nonlinear Feature Interactions remains deferred. Broad model selection belongs
to AFRE-20; Ensemble & Signal Fusion belongs to AFRE-21. Portfolio construction, risk
optimization and execution remain downstream projects.

Fixed gates pin explicit `available_ns` (default0 means a declared policy available from
clock epoch0). Application includes this clock in the availability floor; a future fixed
policy cannot be applied at an earlier origin. Callers must declare the actual policy
availability for later configurations; hashes cannot authenticate that declaration.


## AFRE-13 composition boundary

[Nonlinear interactions](nonlinear-feature-interactions.md) consume these completed
contracts through exact neutral scalar references. Explicit definitions and TRAIN-only
knots/scaling/coefficients/tree splits preserve source availability and actual computation.
TEST cannot choose interactions/splits/knots. Event×regime, microstructure×context,
options×context and expert×state share the generic layer; no direct external-engine
implementation dependency exists. Target-free application, immutable source revisions,
matched later truth, AFRE-9 ranking and bounded replay preserve prior semantics.
Diagnostics are arithmetic/descriptive, not causal importance; no automatic pruning/model
selection or sequence modeling is implemented. Predictive metrics do not establish
profitability. AFRE-14 Temporal / Sequence Models is complete; AFRE-15 Forecast Uncertainty Decomposition remains deferred.


## AFRE-14 sequence integration

Exact causal expert/mixture outputs may become sequence predictors with preserved target/horizon and lineage; expert-combination weights are not portfolio weights.
See [temporal sequences](temporal-sequence-models.md) and [causal sequence training](causal-sequence-training.md).
AFRE-15 uncertainty decomposition remains deferred; predictive metrics do not establish profitability.
