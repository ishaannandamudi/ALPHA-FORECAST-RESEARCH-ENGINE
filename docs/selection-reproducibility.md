# Selection reproducibility and correction semantics

Canonical closed JSON, native seeds/specs, sorted dimensions/values/recipes and
domain-separated content fingerprints determine semantic identity. SearchSpace,
CandidateSpec, SelectionRequest, fit, validation, decision and registry are immutable.
Timing measurements are diagnostic output only, outside artifact identity.

Selection starts from a bounded isolated SQLite backup of a pinned read snapshot.
Native fits and scoring operate on this frozen view. Atomic publication admits only
new immutable rows from the static native table whitelist, checks existing-row equality
and publication bounds, and preserves concurrent unrelated additions. Exact registry
replay checks all native evidence before publishing. No live latest-state substitution
enters an already frozen request.

TRAIN/VALIDATION/TEST second-writer source corrections and later candidate-space
publication cannot change the open selection. A corrected source context requires
an explicit new source build/dataset/fold/recipe/space, creating new candidate/fit/
selection IDs. A new truth cutoff is a new SelectionRequest and AFRE-19 attempt.
Stored validation replay pins original truth IDs; old results retain original bytes.
The demo rebuilds only VALIDATION labels for a correction, retaining original causal
TRAIN labels and then obtaining a new selection identity. TEST correction remains
independent of selection.

Tests verify byte-identical semantic artifacts across seeds0/1/42/random, reversed
dimension/value/recipe/sample order, upstream insertion/request reversals and restart.
Floating-point reproducibility is within the supported platform/native numerical
implementation; universal hardware bit identity is not claimed.

SelectionAudit follows the exact frozen selection graph across native phases, explicit
TRAIN witnesses, scored VALIDATION truth, sources, features and AFRE-19 opportunities.
Embedded recipe/horizon specs remain traversable. Unrelated TEST responses and entire
latest source histories are excluded. Node, depth and serialized byte ceilings fail
closed. Persisted audit refs are immutable and revalidated on replay.

Independent MSE, MAE, R², Gaussian CRPS quadrature/NLL density and empirical CRPS pairwise
oracles are recorded in the [profile](selection-profile.json). Full regression and
offline socket/DNS coverage results are in the [completion report](AFRE_20_COMPLETION_REPORT.md).
No runtime network, eval/exec, pickle, joblib, shell, executable imports, executable
search payloads or provider-selected paths are part of selection. Runtime dependencies
remain empty.
