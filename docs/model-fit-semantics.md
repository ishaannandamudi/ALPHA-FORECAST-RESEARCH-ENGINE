# Model fit and availability semantics

One exact persisted research dataset, split and fold determine TRAIN. Matrix
construction reads one pinned SQLite snapshot. Every response must match the exact
AFRE-2 target, full origin and stable security, with a completed verified label
known by the fold training cutoff; equality is admitted. VALIDATION, TEST, PURGED,
EMBARGOED and INELIGIBLE responses cannot affect coefficients, convergence,
reference statistics, preprocessing or hyperparameters.

DesignMatrix pins spec/dataset/split/fold, target, semantically ordered TRAIN rows,
feature columns in dataset-manifest name order, transformed values, responses,
exact joins/vintages, preprocessing states and explicit missing exclusions.
The target is solely the response vector. Duplicate feature identities, target
columns, nonnumeric values, NaN/infinity and overflow fail. FAIL raises on missing
features; declared SKIP under preserved missing data records exclusions. There is
no model-specific imputation. Mean/reference baselines use the same declared matrix
admission protocol as linear models, making exact-sample comparisons meaningful.

AFRE-4 preprocessing states are supplied exactly and replayed against that fold's
TRAIN boundary; they are never refitted from the whole dataset. Regularized models
require an explicit state for every feature, including an explicit NONE when raw
units are intended. Every fit transformation occurs after state/input availability.

ModelFitInputs pins matrix identity, exact admitted TRAIN order, preprocessing,
training cutoff and supplied UTC fit start/completion/availability clocks. Start >=
cutoff, completion >= start, model availability >= completion and all admitted data
and preprocessing availability. ModelFitRun additionally pins the result artifact
and diagnostics. This two-stage identity avoids a circular run/artifact hash.
The model artifact points to fit inputs; the immutable fit index supplies its exact
completed run. Later corrected datasets produce new lineage/fit identities.

These clocks are caller-supplied evidence; tests use explicit synthetic nanoseconds.
The library neither authenticates a caller's clock nor silently supplies an earlier
fit time. A model completed after a historical origin cannot issue an admissible
historical OOS forecast there. Research manifest construction time is recorded
separately from the historical content availability of its frozen TRAIN inputs.

Fits publish spec, foundation bridge, matrix, inputs, diagnostics, coefficients and
run atomically. Failures publish no partial fit. Actual elapsed timing uses a separate
nonidentity `last_fit_timings` diagnostic. Fixed semantic inputs/clocks give identical
canonical artifacts; no implicit wall-clock read enters identity.
