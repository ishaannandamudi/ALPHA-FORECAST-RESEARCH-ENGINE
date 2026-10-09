# Cross-sectional alpha and ranking

AFRE-9 is a relative-ranking research layer, not portfolio construction. It emits
scores, ranks, coverage and provenance. It never emits position sizes, allocations,
orders, leverage or execution decisions. Predictive metrics do not establish trading
profitability. Engine **0.10.0**, cross-sectional schema **1.0**, shared store **1.9**,
SQLite `user_version=10`; earlier public schemas remain 1.0.

`CrossSectionIdentity` pins a representative full ForecastOrigin, exact AFRE-2 target
and typed horizon, AFRE-3 snapshot, eligibility policy and security order. Across
securities, timestamp, availability cutoff, calendar/session, build context and
universe projection must agree exactly. The instrument is the comparison dimension;
it is the only ForecastOrigin field allowed to differ. `CrossSectionSpec` adds exact
model/provider statistic, direction, ties, missingness, normalization, group policy,
ranking layer, historical-delivery approval and implementation version.

One frozen read snapshot builds the exact INCLUDED and ELIGIBLE security grid. All
eligible securities remain in `CrossSectionRanking.entries`, canonically sorted by
stable security fingerprint. Extra/ineligible securities and duplicates reject.
Missing, unsupported, invalid and future sources remain explicit. EXCLUDE_MISSING
and RETAIN_UNRANKED both preserve the audit grid; FAIL_ON_MISSING rejects the build.
Neither policy imputes values. Ranked count/eligible count is coverage. Reasons and
exact group references expose exclusion composition; missingness can bias results.

Each observation pins its own full origin, source and optional PIT membership,
plus the snapshot's exact listing. Issuer enrichment is reserved until exact issuer
evidence is supplied; it is not guessed. RawScore preserves the original sign and
value. Global peer state and group-neutral peer state have separate immutable IDs.
The supplied ranking layer chooses RAW, NORMALIZED or GROUP_NEUTRAL explicitly.

Rank **1 means best**. HIGHER_BETTER and LOWER_BETTER are supplied choices. Exact
numeric ties support AVERAGE_RANK, MIN_RANK, MAX_RANK and DENSE_RANK. No tolerance
merges nearby scores. Percentile is `1-(rank-1)/(N-1)` for N>1; a singleton pure-rank
query returns 0.5. Dense ranks use the same declared N denominator and need not span
the full percentile range. Transformations require an explicit minimum N>=2.

ScoreSource supports POINT_PREDICTION, POINT_EXPECTATION, MEDIAN, QUANTILE,
THRESHOLD_PROBABILITY and EXTERNAL_SIGNAL. Exact model/state/provider versions and
quantile/event definitions are identity-bearing. Raw and calibrated distributions
remain distinct. An unsupported expectation or unrequested quantile/event remains
unranked; there is no guessed distribution. No uncertainty penalty is implicit.

Included predictors and group memberships must be usable by the origin cutoff.
Physical ranking computation is at or after the origin and no later than its cutoff;
the currently supported causal build therefore requires cutoff=origin and computation
at that instant. Later retrospective composition is not backdated into a historical
ranking. Qualified historical delivery concerns input evidence, not fabricated rank
computation. Ranking application reads no current/future target truth.

AFRE-8 horizons are ranked independently. Exact rich target, benchmark, adjustment,
calendar and horizon identities prevent mixing simple/log/residual outcomes or
different horizons. There is no cross-horizon fusion or aggregate rank surface.

`CrossSectionRepository` adds three immutable tables, verified lookup indexes,
canonical safe JSON and additive transactional 9→10 migration. Prior payloads,
DDL and metadata remain unchanged. Exact repeat is idempotent; conflicting stored
bytes reject. Startup validates the full layout; reads check hash/schema/indexes;
deep audit replays membership, scores, transformations, rank, truth and diagnostics.
One bounded lineage spans earlier fits, folds, features, targets and universe evidence.
Backdated corrections require explicit new references and preserve old bytes.

Default bounds: 10,000 securities, 1,000 groups per cross-section, 100,000 stored
external signals/group records, 128 features, 100,000 truth rows/rankings, 10,000
series observations, 100,000 lineage nodes, depth64 and 8MiB serialized/audit bytes.
Hard limits include 100,000 securities and 16MiB canonical payloads. Overflow fails.

See [normalization](cross-sectional-normalization.md), [groups](group-neutral-ranking.md),
[IC](information-coefficient.md), [stability](rank-stability.md),
[external integration](external-signal-integration.md), [profile](cross-sectional-benchmark.md)
and [completion evidence](AFRE_9_COMPLETION_REPORT.md).

## AFRE-10 integration

AFRE-10 supplies neutral derived scores from exact conditioned forecasts. Same full origin, target/horizon, PIT universe and exact groups remain enforced. A wrapper records affected/unaffected securities. Event IC shares the exact matched truth set; ranking remains predictive research, with portfolio construction downstream.
See [event-conditioned forecasting](event-conditioned-forecasting.md).

## AFRE-11 composition boundary

[Regime conditioning](regime-conditioned-forecasting.md) consumes exact causal
filtered hard/soft state evidence without changing this phase's contracts. As-of
is distinct from all six availability clocks. TRAIN state means/fitted-residual
offsets, fixed soft weighting and explicit fallback are horizon-specific. Application
preserves exact base bytes and reads no truth. Matched evaluation/ranking retains
PIT scope and TEST controls. Global calibration cannot silently transfer, and
descriptive regime drift never refits. MCE/AME remain external neutral data producers;
downstream HFT integration supplies adapters. Predictive metrics do not prove profitability.

## AFRE-12 composition boundary

[Mixture of Experts](mixture-of-experts.md) preserves exact native/neutral producer identity,
target/horizon compatibility, receipt-aware availability, causal gating inputs and missingness.
Fixed gates and one TRAIN-only constant simplex fit remain explicit. TEST never changes weights.
Finite Gaussian/empirical laws preserve components; quantile averaging is invalid. Component
calibration != mixture calibration. Matched truth/contribution/correlation/drift diagnostics and
same-origin rankings remain descriptive and never refit/select. No independence or profitability
is claimed; expert weights are forecast-combination weights, never portfolio weights. Downstream
HFT integration supplies AME/MCE/EIE/options adapters without direct implementation dependencies.
Frozen snapshots, append-only corrections and bounded lineage preserve older artifact bytes.


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
profitability. AFRE-14 Temporal / Sequence Models is complete; AFRE-15 Forecast Uncertainty Decomposition is complete; AFRE-16 Signal Orthogonalization & Redundancy Analysis is complete; AFRE-17 Invariance & Stability Research is complete.

## AFRE-16 integration

Explicit orthogonal residuals can feed unchanged AFRE-9 ranking. Historical cross-sectional projection fits complete eligible TRAIN grids and applies frozen coefficients within later origins. Exact PIT universe and supplied historical sector memberships remain mandatory; no portfolio sizing follows.

See [signal orthogonalization](signal-orthogonalization.md). Supplied candidate/reference sets are fixed;
no automatic pruning or broad signal search occurs. Orthogonal != independent, residuals are not
guaranteed alpha, and predictive metrics do not establish trading profitability. The frozen roadmap
remains26 distinct phases, AFRE-0 through AFRE-25; AFRE-17 Invariance & Stability Research is complete.

AFRE-17 adds [declared environment stability research](invariance-stability-research.md) over frozen artifacts. PIT memberships, target/horizon compatibility, exact intersections and minimum counts remain explicit. Input shift and error degradation are separate; there is no causal-proof, significance, profitability, auto-refit/prune or promotion claim. AFRE-18 [cost-aware research evaluation](transaction-cost-aware-research.md) is complete.

AFRE-18 [explicit hypothetical cost research](transaction-cost-aware-research.md) now
evaluates frozen native forecasts/residual signals using separate exposure, cost and later
truth artifacts. Gross and net remain separate; PIT cohorts retain full-path trade deltas.
Uncertainty does not automatically become cost and ranking/stability definitions are unchanged.
Historical-causal versus ex-post evidence is explicit, and supplied grids cannot select TEST
settings. No execution, model selection, direct external-engine dependency or profitability
proof is added. AFRE-19 Multiple Testing & Research Overfitting Controls is complete; see [the control layer](multiple-testing-controls.md).
