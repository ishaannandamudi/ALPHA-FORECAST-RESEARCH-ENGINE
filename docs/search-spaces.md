# Declared discrete search spaces

SearchSpace contains categorical DiscreteDimensions and a complete explicit native
recipe for every Cartesian combination. Labels identify variants; they are never
executed as parameter expressions. Each recipe embeds its closed native model spec,
seed, TRAIN inputs/bindings, VALIDATION feature bindings, preprocessing identities,
feature identities and optional diagnostic references. Native APIs determine actual
model semantics. Relabeling cannot invent an unsupported native capability.

Dimensions, values, recipes and requested samples normalize deterministically and
reject duplicates. CandidateSpec pins the complete parent space plus recipe and
exact dataset/fold/target/horizon. Enumeration sorts candidate fingerprints, with a
hard maximum of 128 candidates and 16 dimensions. The complete grid and deterministic
resource reservations are checked before any candidate fit. There is no truncation.

The declaration clock must precede the fold TRAIN cutoff. This is a caller-recorded
protocol assertion, not proof that nobody privately inspected outcomes. Criterion,
optional secondary criterion, minimum support, single-valid policy, baseline recipe,
failure anchors and fingerprint tie rule are identity-bearing. SelectionRequest
separately pins the truth cutoff and result availability clock. A different cutoff
creates new validation identities and distinct AFRE-19 attempts.

Feature/preprocessing variants need exact native feature and TRAIN-state witnesses.
For nonlinear and sequence models, actual declared feature definitions and bindings
must match. AFRE-16 residual inclusion is explicit and must be consumed by the native
nonlinear input, with projection/source/sample/availability proof. Merely attaching
a residual ID does not make it a feature. No automatic inclusion or pruning occurs.

One search owns one target, horizon and fold. Actual one-hour and one-day fixtures
select independently with distinct IDs. Independent fold calls support walk-forward
research; aggregate/nested fold selection and shared coupled-horizon optimization
are deferred. Adaptive, random, Bayesian, continuous and bounded-partial searches
are unsupported. A later candidate requires a new space and cannot enter an old pool.
