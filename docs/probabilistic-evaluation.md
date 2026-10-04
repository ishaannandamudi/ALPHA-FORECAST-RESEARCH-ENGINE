# Causal probabilistic evaluation, persistence and replay

ProbabilisticEvaluation pins one exact artifact, dataset/fold, target/horizon,
forecast scope, requested forecasts, used sample/target/truth pairs, exclusions,
protocol, explicit truth cutoff and final evaluation availability. Different models,
scopes or target definitions cannot be pooled. Forecasts must exist and be available
by evaluation cutoff. Exact pinned TargetVintage must match rich target and full
origin and have completed, verified truth available <= cutoff. Equality is admitted.
Later corrections never silently replace the pinned evaluation truth.

IN_SAMPLE is retrospective and separate from VALIDATION/TEST/other OOS. TEST uses
existing AFRE-4 TestEvaluation semantic seal and immutable identity/purpose/cutoff
reuse history. Missing identity, changed reuse cutoff or truth outside the seal
fails; TEST cannot be relabeled validation or other OOS. The seal is research
boundary evidence, not authentication or AFRE-19 multiple-testing governance.

Evaluations report proper scores, per-origin groups, per-quantile empirical frequencies,
explicit central interval coverage/width and fixed-bin PIT histogram/mean. Coverage
includes both quantile endpoints. PIT is the right CDF at truth, nonrandomized at
empirical atoms; ties/discrete distributions do not imply a uniform PIT benchmark.
QUANTILE_SET has no PIT and reports an empty-count histogram of declared shape.
No rolling calibrator, bin-conditioned reliability fit, per-security grouping or
calibration transform exists. AFRE-6 evaluates calibration diagnostics but does NOT
fit calibration transformations. AFRE-7 owns Forecast Calibration.

ProbabilisticComparison requires identical dataset/fold, target/horizon, scope,
cutoff, evaluation protocol, exact sample/target/truth sets, exclusions, forecast
count and score-level/event keys. Deltas are candidate minus reference, including
NLL/CRPS/pinball/Brier where both supported. No common-subset trimming or model
selection occurs. Comparisons remain descriptive; no prediction metric establishes
trading profitability.

ProbabilisticLineageAudit traces artifact/run/input/state/spec -> exact completed
point fit/matrix -> frozen fold, TRAIN samples, features/vintages/preprocessing and
TRAIN targets. Forecast adds point forecast and origin/input evidence, without
expanding held-out truth through the ResearchSample edge. Evaluation explicitly
adds later used truth and protocol/TEST evidence. One shared depth/node/byte budget
spans probability, point and upstream layers. Cycles, unresolved links and overflow
fail. Whole-store audit replays fitted uncertainty, forecasts, scores and index links.

ProbabilisticRepository adds five immutable tables and spec/base/family/fold/target,
dataset/split/fit, security/origin/scope and evaluation-cutoff indexes. Migration 6->7
is additive and transactional, preserving every previous row, DDL and metadata value;
injected failure restores 1.5/user_version=6. New metadata identifies schema1.0,
engine0.7.0 and store1.6. Future versions or changed layouts fail closed. Fixed canonical
structured data only: no executable imports, pickle, joblib, shell, network or paths
selected by providers. Reads check class/schema/hash/bounds and independent indexes;
semantic validation is mandatory on publication and whole-store/lineage audit.

Defaults bound 50,000 observations, 64 quantiles/thresholds, 10,000 forecasts and
stored evaluations/history, 2,000,000 query/scoring work cells, 100,000 audit nodes,
depth64 and 8MiB serialized bytes (hard decoder ceiling16MiB). Overflow rejects;
no silent truncation or streaming. Empirical forecasts embed the pool: byte/work
budgets intentionally constrain pool-times-batch growth.

Seeds0/1/42/random, reversed upstream/TRAIN/request insertion and restart replay
identical canonical artifacts on the supported Python/platform arithmetic environment.
Cross-platform bit identity is not promised. Caller-supplied clocks require external
physical delivery evidence; the library does not authenticate them. A concurrent
second writer correction leaves the pinned fit unchanged; rebuilt point/probabilistic
models have new identities and old bytes remain intact.

The [offline demo](../examples/probabilistic_demo.py) covers response denial, held-out
perturbation, exact-sample unconditional comparison, correction and restart. The
[profile](../benchmarks/probabilistic.py) measures a two-horizon persisted pipeline
separately from 4,000 synthetic TRAIN residuals. Canonical upstream provenance limits
registry scaling; numerical-kernel results do not claim equivalent registry throughput
or a production SLA. Portfolio construction, risk optimization and execution remain
downstream. Model selection, ensembles and AFRE-7 calibration are deferred.
