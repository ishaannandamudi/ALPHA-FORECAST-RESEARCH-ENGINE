# Alpha Forecast & Research Engine — master specification

Status: **AFRE-0 through AFRE-7 complete**, engine 0.8.0,
foundation/feature-store/target/universe/dataset/model/probabilistic/calibration schemas 1.0,
shared calibration store 1.7/user_version=8.

## Mission and philosophy

AFRE is the predictive research layer of a quantitative architecture. Its eventual
question is: given information actually available at origin T, what is the
conditional distribution of future asset returns across horizons, how uncertain
is it, which inputs drove it, and does it survive honest out-of-sample evaluation
and realistic frictions? Research hygiene precedes model complexity.

The eventual output is a distribution: mean, median, variance, quantiles,
probabilities, expected absolute move, intervals, tails, calibration diagnostics,
and explicit provenance. AFRE-0 implements **no prediction or fitting**. A research
result is not a trading strategy. Portfolio construction, sizing, orders, execution,
and profitability claims are outside this engine.

## Architecture and trust boundaries

The package has four layers: immutable typed contracts; pure temporal/identity
validation; deterministic serialization and hashing; an append-only SQLite
artifact registry. Provider protocols describe external boundaries. No sibling
repository is read or imported. SQLite is AFRE's own registry, never a coupling
to EIE internal tables. Dependency direction is contracts → validation → consumers;
storage and providers cannot relax contract invariants.

EIE contributes final snapshot metadata through a provider-neutral as-of contract.
MCE, options, and AME are optional future providers. Adapters must preserve stable
instrument identity, knowledge cutoff, upstream engine/schema versions, component
fingerprints, source versions, and availability. AFRE does not reimplement their
analytics. AFRE-1 supplies offline neutral market/EIE adapters and the feature
store; optional MCE/options/AME implementations remain deferred.

## Temporal semantics

Canonical time is a nonnegative UTC integer nanosecond, bounded to signed 64-bit.
No floats, naive datetimes, local-time strings, implicit wall-clock reads, or
precision-losing conversions enter identities. Origins contain stable security,
timestamp, availability cutoff, market session, build context, and universe ID.
The availability cutoff cannot exceed origin time; equality is admissible only
when the source proves availability at that instant.

Valid/effective time describes when a fact applies. Observed time describes when
the source observation occurred. Available time describes when research could
actually use it. A quarterly fundamental can have a much earlier effective time
than publication. Effective time need not precede observation for scheduled facts.
Observation cannot follow availability. Revisions form new artifacts.

Derived availability is at least the maximum of all dependency availability and
computation availability. A historical reconstruction additionally records a
proof artifact and the availability of the originally reproducible computation;
without that proof, the actual computation timestamp governs. Reconstruction
is evidence supplied by a provider, not a license to backdate inputs.

## Feature semantics

Features carry typed definitions, versions, value types, units, scope, semantic
type, lookback, availability rule, missing policy, transformation version and
declared dependency identities. Values carry the exact definition, stable entity,
effective/observed/available time, source version, quality and lineage. Immutable
parameter tuples replace mutable arbitrary dictionaries. Feature and target
namespaces are disjoint; dependencies can reference only feature artifacts and
definitions. A feature row checks identity, definition agreement, universe
context, duplicate definitions, and every feature's availability at its cutoff.

Missing, not applicable, not available yet, stale, invalid and unknown are separate
states. None is a value only when an explicit absence state accompanies it; zero
is an observed numeric value. Stale/invalid values are withheld in AFRE-0. Missing
policy describes later handling; no imputation or normalization occurs here.

Contracts prevent typed target injection and explicit future dependencies. They
cannot prove the truth of a provider's scalar value or claimed timestamp. Future
adapters must audit derivation, raw vintages, publication clocks and evidence.

## Horizons and targets

Elapsed time, trading sessions and bars are separate typed bases. Identities
include nanosecond duration or count, calendar/session version or bar definition
where relevant, and endpoint convention. A day of elapsed UTC time is distinct
from a trading session. Foundation session/bar rows require explicit calendar/market
resolver evidence; AFRE-2 supplies exact schedules and observation selection.
AFRE-0 never pretends these horizons are fixed elapsed durations.

Target specifications define simple/log/residual/absolute return, realized
volatility, downside return, and maximum adverse/favorable excursion. Residual
returns require an explicit benchmark identity. The only foundation price
convention is first admissible observation strictly after T through the last
admissible observation at or before the resolved endpoint: **(T, endpoint]**.
Target rows preserve an explicit window and availability at or after its end,
market dataset fingerprint, quality, and value. AFRE-0 itself calculates no labels.
Training eligibility requires a completed, available, acceptable target and an
origin strictly before the fit cutoff. Test origins must follow fit cutoff.

## Universe, security and adjustment semantics

Stable security IDs are namespaced opaque identities; a ticker is only a temporal
mapping. Membership has a half-open valid interval [from, until), independent
knowledge time and source. Every historical selection applies both clocks.
Current-constituent reconstruction is explicitly rejected. Delisted securities
remain representable. Reused tickers cannot merge separate stable IDs.

Adjustment policies distinguish raw, split adjusted, total return and explicit
adjustment streams. Non-raw policy requires identified adjustment data and its
knowledge cutoff. Foundation DatasetManifest origins cannot precede that cutoff.
AFRE-2's separate TargetDatasetManifest instead admits forward action evidence by
the declared target source cutoff and label computation time. Each target pins
exact policy/stream knowledge; no future action can become a forecast-time feature.

## Datasets and experimental identity

A manifest commits to time range, historical universe, definitions, targets,
source fingerprints, calendar, adjustment and missing policies, engine version,
and processing implementation version. Separate source identity from processing
identity. Unordered semantic sets are sorted and duplicates rejected before
hashing. A feature set has its own identity. Build context IDs are descriptive
labels; manifests and experiment specs provide the content identity.

An experiment commits to dataset, universe, feature set, target, split policy,
model specification, random seed, evaluation policy, costs and code version.
Cross-references must agree. Model identity includes family, hyperparameters,
features, target/horizon, training policy, explicit seed and implementation version.
Artifact metadata retains fit cutoff, dataset fingerprint, safe serialization
format, opaque bytes hash, metric references and created availability. No model
loader, estimator, registry of executable plugins, or pickle format is provided.

## Research methodology and validation

Future builders must construct features only from vintages known at each origin,
labels only after completion, and universes from historical membership. Scaling,
imputation, feature selection and normalization fit exclusively inside training
folds. Overlapping labels require interval-based purging and embargo. AFRE-0
records explicit train/validation/test intervals, cutoffs, purge and embargo
policy and checks ordered disjoint ranges; it does not claim to implement purged
walk-forward splitting. Model and experiment selection must not consume the
held-out test window. Repeated test access belongs in the later research registry.

Evaluation will measure probabilistic scoring, calibration, discrimination,
cross-sectional skill, stability across periods/regimes and net informational
value after declared friction assumptions. Selection must include multiple-test
controls, sensitivity analyses, benchmark comparisons and failed experiments.
AFRE-0 metric references are finite named/versioned values with sample count and
evaluation range, not a sophisticated evaluation engine.

## Lifecycle, risks and downstream boundary

Specs precede runs. Results record planned/completed/failed state, realized ranges,
input hashes, model metadata reference and creation availability. Completed
results require a model artifact reference. Failures require a reason. Corrections
produce new immutable records; no last-write-wins mutation. Later model lifecycle
adds selection, calibration, decay/drift monitoring and retirement. Temporal
correctness alone does not establish causal identification, tradability,
stationarity or economic value. Cost-aware evaluation is research, not execution.

Downstream consumers will receive typed forecast snapshots and uncertainty with
provenance. They own risk, portfolio allocation and execution. AFRE has no trading
commands or operational credentials.

## Security and reproducibility

Canonical JSON uses UTF-8, sorted keys, compact separators, finite floats, explicit
type/enum tags, no duplicate JSON keys, and signed zero normalization. SHA-256
uses an AFRE/schema/domain prefix. Only a closed allowlist of contract classes and
enums can be reconstructed. No eval, exec, pickle, dynamic imports, network,
source-chosen filesystem paths, or shell execution occurs in the package. Store
path is chosen by its caller; model byte hashes are references, never load paths.

SQLite migration 0→1 is deterministic and transactional. Unknown schema versions,
unexpected layouts, noncanonical payloads, corrupted hash/index data, and missing
immutability protections fail closed. Explicit transactions roll back on failure.
UPDATE/DELETE triggers protect registry artifacts. Triggers do not protect against
an administrator rewriting the file; read-time validation detects inconsistency,
but hashes alone are not signatures or a malicious-source authenticity proof.

Reproducibility is verified across parameter insertion order, process hash seeds
and database restart. Zero runtime dependencies; Python 3.11+. Offline tests block
sockets. Quality gates: full pytest; ≥95% combined branch/statement coverage;
Ruff lint/format; strict mypy; hash-seed/restart/corruption/migration checks; README
example; diff whitespace/full review; secret and unfinished-work scans; benchmark.
Benchmark measurements are local evidence, not a production SLA.

## Frozen advanced roadmap and acceptance boundaries

The project freezes **26 distinct phases, AFRE-0 through AFRE-25**. Each phase
retains its own scope and acceptance evidence; these concerns must not be merged
back into larger phases. Completed AFRE-0 contracts remain unchanged.

| Phase | Name | Deliverable and principal research concern |
| --- | --- | --- |
| AFRE-0 | Foundation, Contracts & Temporal Semantics | Foundation contracts, temporal semantics, identities, immutable registry and reproducibility; no feature store or fitting |
| AFRE-1 | Point-in-Time Feature Store | Feature registry, immutable vintages, computation DAG, point-in-time joins, stale/missing semantics, materialization, training/serving parity, normalization lineage, efficient history and audited neutral adapters; feature store only |
| AFRE-2 | Forecast Targets & Label Construction | Exact admissible price endpoints, action-aware labels and target completion/availability clocks |
| AFRE-3 | Point-in-Time Universe & Security Eligibility | Historical membership, eligibility, delistings, stable security identity and symbol history |
| AFRE-4 | Dataset Builder & Leakage-Safe Splitting | Dataset construction, interval purging, embargo, walk-forward folds and fold-local preprocessing |
| AFRE-5 | Statistical Baseline Models | Honest statistical baselines and out-of-sample benchmark evidence |
| AFRE-6 | Probabilistic Forecasting | Predictive return distributions, quantiles and proper probabilistic scoring |
| AFRE-7 | Forecast Calibration | Out-of-sample probability/interval calibration and reliability diagnostics |
| AFRE-8 | Multi-Horizon Forecast Architecture | Consistent horizon endpoints and coherent multi-horizon forecasts |
| AFRE-9 | Cross-Sectional Alpha & Ranking | Historical-universe-aware ranking, cross-sectional predictive skill and evaluation |
| AFRE-10 | Event-Conditioned Forecasting | Event-conditioned relationships with publication, availability and reaction clocks |
| AFRE-11 | Regime-Conditioned Models | Regime conditioning without future regime inference |
| AFRE-12 | Mixture of Experts | Expert specialization and learned gating with leakage-safe training and evaluation |
| AFRE-13 | Nonlinear Feature Interactions | Nonlinear relationships and interaction effects with honest out-of-sample evidence |
| AFRE-14 | Temporal / Sequence Models | Sequence models with causal lookbacks, temporal alignment and leakage-safe evaluation |
| AFRE-15 | Forecast Uncertainty Decomposition | Aleatoric, epistemic and data uncertainty with identifiability limits |
| AFRE-16 | Signal Orthogonalization & Redundancy Analysis | Redundancy, orthogonalization and incremental predictive information |
| AFRE-17 | Invariance & Stability Research | Relationship stability across periods, regimes, universes and distribution shifts |
| AFRE-18 | Transaction-Cost-Aware Research Evaluation | Friction-aware research evaluation with explicit cost assumptions; no portfolio construction |
| AFRE-19 | Multiple Testing & Research Overfitting Controls | Multiple-testing corrections, selection-bias controls and protected final holdout |
| AFRE-20 | Hyperparameter & Model Selection Framework | Nested tuning and reproducible model selection, separate from ensemble construction |
| AFRE-21 | Ensemble & Signal Fusion | Signal fusion and ensembles trained with out-of-fold inputs |
| AFRE-22 | Drift, Decay & Model Health | Drift detection, predictive decay and model-health monitoring |
| AFRE-23 | Champion/Challenger & Shadow Evaluation | Champion/challenger comparison and shadow forecast evaluation before service promotion; no trade execution |
| AFRE-24 | Forecast Snapshot, Registry & Service | Final typed forecast snapshot/service boundary, provenance registry and reproducible artifact replay |
| AFRE-25 | Final Integration, Hardening & Research Audit | End-to-end integration, security/operational hardening and final research audit |

AFRE-18 evaluates research under trading frictions; portfolio construction remains
a downstream responsibility. AFRE-19 keeps multiple-testing and research
overfitting controls explicit. AFRE-20 selects models; AFRE-21 constructs ensembles.
AFRE-22 monitors drift and decay; AFRE-23 separately evaluates champions,
challengers and shadow forecasts for deployment decisions. AFRE-24 is the final
forecast service boundary; AFRE-25 completes integration, hardening and audit.

Portfolio construction, risk optimization and execution remain **downstream
projects after AFRE**. No AFRE phase may claim trading profitability merely from
predictive metrics.

The roadmap may evolve through a reviewed specification revision while preserving
these distinct phases. **Stop after AFRE-7.** AFRE-1 remains only the
Point-in-Time Feature Store. AFRE-6 implements explicit TRAIN-only uncertainty,
causal distributions and proper scoring. AFRE-7 adds separate causal calibration.
AFRE-8 — Multi-Horizon Forecast Architecture is next; model selection, ensembles,
portfolios and execution remain deferred.

## AFRE-1 implementation and availability boundary

Engine 0.2.0 preserves foundation schema 1.0 and adds feature-store schema 1.0.
`FeatureStoreRepository` upgrades the SQLite registry additively and transactionally
from store 1.0 to 1.1 (user_version 1 to 2), preserving foundation rows and metadata.
The original `ArtifactStore` remains a strict legacy 1.0 reader/writer; use the
feature-store repository for migration and shared access to the upgraded database.

Immutable registered definitions, exact vintages, qualified delivery evidence,
explicit scope mappings, static computation DAGs, supplied normalization state,
receipts, audits and materializations establish point-in-time feature history.
One indexed as-of function serves single lookups and historical joins within
consistent read snapshots. Ambiguous equal-time vintages require predecessor
precedence. Frozen materializations retain exact historical selections after
later/backdated inserts.

Externally sourced features distinguish upstream publication, upstream source
availability, actual AFRE receipt, ingestion, computation and final availability.
Provider publication is not AFRE availability. Without locally approved qualified
historical delivery evidence, final availability >= actual AFRE computation >=
receipt. Qualified reconstruction retains actual later physical clocks and exact
source/entity evidence rather than pretending historical literal AFRE ingestion.
Live latency, months-later archive and qualified replay tests are mandatory
acceptance evidence. Derived outputs additionally respect input and supplied
normalization-state availability bounds.

AFRE-1 implements no predictive models, learned fold preprocessing, splitting,
labels, portfolio construction or execution. The standalone documentation and
offline example/benchmark specify supported policies and limits; no predictive
metric establishes trading profitability.

## AFRE-2 target truth and acceptance boundary

The additive `afre.target_engine` package preserves every AFRE-0/1 public contract
and migration. Rich `TargetDefinition` and target-only source/vintage/dataset types
remain separate from foundation `TargetSpec`, whose original first-after-origin
semantics remain unchanged. No implicit cast substitutes richer endpoint policies.
New target identity domains are blocked by unchanged AFRE-1 lineage safeguards.
Target rows cannot enter feature persistence, computation DAGs or normalization.

The nominal elapsed outcome interval is (T,T+H]. Default AFRE-2 origin/endpoint
prices are exact completed closes, with separately declared bounded alternatives
and typed tolerance flags. Exact supplied UTC session grids resolve session/bar
horizons, holiday/short-session/extended-hours behavior and path sampling. Values
are dimensionless simple/log/residual/absolute/downside returns, close-path realized
volatility and signed adverse/favorable excursions. Volatility uses summed squared
consecutive log returns, explicit sampling and optional explicit annualization.
Missing paths fail by default; explicit partial coverage is withheld from training.

Raw, split and supplied price-factor adjustments are separate target policies with
exact action-stream coverage and knowledge clocks. Total return/dividend reinvestment
remains contract-only and fails clearly. Residuals subtract an exact aligned supplied
benchmark; there is no beta fitting or implicit benchmark/universe construction.
Missing prices, zero outcomes, halts and delistings retain explicit rows/states.

Source builds freeze exact admitted bars, calendar, action stream, benchmarks and
cutoff. Label datasets freeze exact origins/universe, definitions, inputs, rows,
construction time and engine/builder versions. Source corrections/rebuilds create
new identities and never mutate frozen truth. Indexed known-by queries require
completed verified labels with origin before cutoff and availability ≤ cutoff.
Every source/output retains six availability clocks; live receipt and late endpoint,
benchmark/action delivery constrain availability. Qualified historical source evidence
retains actual later reconstruction clocks; target computation is never silently
backdated. No qualified historical target-computation contract is implemented.

`TargetRepository` adds store 1.2/user_version=3 transactionally; old rows/metadata
remain byte-identical. Normal reads validate bounded payload/hash/index integrity;
deep audit replays exact calculations and referenced evidence. Offline tests cover
availability, calendars, paths, actions, isolation, revision/order/hash-seed/restart,
concurrent writers, migration rollback, corruption and bounds. The profile uses
20,000 observations and 12,000 labels; timings are local evidence with no SLA.
See [target contracts](forecast-targets.md), [completion report](AFRE_2_COMPLETION_REPORT.md)
and [benchmark](target-benchmark.md) for policies, gates and limits.

## AFRE-3 completed scope

AFRE-3 implements only Point-in-Time Universe & Security Eligibility. Typed
stable issuer/security/listing identities remain distinct. Symbols, external
identifiers, relationships, lifecycle, listings and constituent evidence preserve
[start,end) valid and knowledge intervals plus all six delivery clocks. Provider
publication is not AFRE receipt; locally approved historical-delivery evidence can
qualify reconstruction without fabricating physical ingestion time.

Universe definitions pin source category, calendar and independent eligibility
policy. Current constituents cannot reconstruct history. Membership is INCLUDED,
EXCLUDED, UNKNOWN or CONFLICTED; absent evidence is exclusion only under an explicit
complete source contract. Known future membership remains separate from effective
membership. Delisted, acquired and spun-off histories retain original stable IDs.

Eligibility reports state, typed reason, exact listing and source/market evidence.
It uses frozen AFRE-1 security-scoped completed observations, per-observation
revision precedence, freshness and delivery qualification; price, trailing share
volume and mean dollar volume exclude future effective/delivery times. The trailing
window is (T-lookback,T], listing age counts supplied completed sessions, and
currency mismatches cannot invoke implicit FX. No imputation or borrow model exists.

Snapshots pin exact security/member/eligibility references and an immutable input
build, with explicit COMPLETE/KNOWN_GAPS/UNKNOWN status. Construction uses one
consistent SQLite read transaction. Later or backdated inserts cannot change old
materializations. Bounded indexed histories, resolution and audits fail explicitly
on overflow or conflict. Store migration 3→4 adds only universe tables, indexes,
immutable triggers and metadata; all previous artifacts and schemas remain intact.

A complete causal snapshot projects to the existing foundation UniverseManifest
at exactly its origin nanosecond. The snapshot fingerprint determines manifest
and downstream dataset identity. Existing feature/target rows join on full stable
security/origin/universe identities; symbols never become primary keys. Queries
with later knowledge can describe revised history but cannot be projected into an
earlier causal forecast origin. See [PIT universes](point-in-time-universes.md),
[eligibility](security-eligibility.md), [completion report](AFRE_3_COMPLETION_REPORT.md)
and [profile](universe-benchmark.md).

AFRE-4 now composes these immutable universe projections without changing prior
contracts. Universe replay retains each persisted snapshot's original engine version.

## AFRE-4 completed scope

AFRE-4 implements Dataset Builder & Leakage-Safe Splitting in a separate
`afre.research_datasets` package. Exact snapshot/security/origin/feature/target
selections freeze under one upstream read snapshot, then publish atomically. Failed
cells remain explicit; backdated corrections produce new builds and old bytes replay.
Typed source/calendar/adjustment compatibility prevents accidental cross-build joins.

Research samples retain actual target intervals, full declared information intervals,
selected vintage IDs and target availability. Temporal holdout, walk-forward, rolling
and expanding folds assign disjoint TRAIN/VALIDATION/TEST/PURGED/EMBARGOED/INELIGIBLE
memberships. Security/issuer/sector/market/global interval purge uses sorted indexes;
elapsed/session/bar embargo uses exact calendars/grids, endpoint inclusion and direction.
TRAIN requires exact completed verified labels known at cutoff, including equality.

Simple fold-local normalization reuses AFRE-1 specs/states and fits only TRAIN, with
explicit missing skips, zero-scale and application availability. Test evaluation
identities record holdout reuse; nested preparation constrains candidates to parent
TRAIN. Neither constitutes model-selection or multiple-testing governance. Bounded
contamination audits recompute frozen grid, partitions, labels and fit statistics.
Store 1.4/user_version=5 adds immutable research artifacts/indexes transactionally.

See [datasets](research-datasets.md), [splitting](leakage-safe-splitting.md),
[purge](purged-walk-forward.md), [embargo](embargo-semantics.md),
[preprocessing](fold-local-preprocessing.md) and [audits](dataset-contamination-audits.md).

## AFRE-5 completed scope

AFRE-5 adds `afre.statistical_models`, preserving the original foundation model and
experiment contracts. BaselineModelSpec composes foundation ModelSpec and pins rich
target/horizon, exact feature set, fold/preprocessing, fixed penalties, explicit
intercept/rank/conditioning/convergence/missing policies, seed and solver/version.
Mean, median, supplied reference, causal persistence, OLS, ridge, lasso, elastic net,
global cross-sectional and supplied-residual linear models fit only exact TRAIN.

One pinned input snapshot freezes a semantically ordered matrix with completed
verified labels known by cutoff and exact supplied AFRE-4 preprocessing. Immutable
fit inputs/runs, coefficients and diagnostics record clocks and complete lineage.
Pivoted Householder QR and augmented ridge avoid matrix inversion; cyclic coordinate
descent uses exact sum-loss L1/L2 conventions and explicit KKT/nonconvergence handling.

Feature-only point prediction never loads target truth and enforces model/input
availability at the origin. Retrospective IN_SAMPLE diagnostics are marked separately.
Later explicit evaluation joins pinned truth for point errors, R², correlations,
per-origin IC/rank diagnostics and identical-sample baseline deltas. TEST evaluation
records existing AFRE-4 access/reuse evidence; no metric can change a model spec.
Store 1.5/user_version=6 adds immutable model artifacts/indexes transactionally.

See [baselines](statistical-baselines.md), [fit clocks](model-fit-semantics.md),
[solvers](linear-models.md), [regularization](regularization-semantics.md),
[evaluation](point-forecast-evaluation.md) and [replay](model-reproducibility.md).

## AFRE-6 completed scope

AFRE-6 adds `afre.probabilistic` above exact completed AFRE-5 point models. Closed
EMPIRICAL_RESIDUAL, GAUSSIAN_LOCATION_SCALE and QUANTILE_SET families pin rich target,
fold/cutoff, ordered TRAIN evidence, RAW/CENTER_MEAN centering, population STD,
explicit MAD factor or fixed positive Gaussian scale, median-bearing quantiles,
strict/inclusive event definitions and numerical versions. Unconditional TRAIN
response distributions require an exact TRAIN-mean admission scaffold.

One pinned snapshot fits only the admitted TRAIN matrix; held-out/excluded labels
never affect uncertainty. Zero continuous scale rejects atomically; discrete and
sparse-quantile degeneracy remain explicit. Probabilistic input/state/artifact/run
clocks are causal. Forecasts use fitted uncertainty and feature-only point prediction
without target or training-response reads; later evaluation joins pinned truth at
an explicit cutoff. Retrospective IN_SAMPLE stays separate; TEST preserves existing
AFRE-4 reuse evidence. Sparse quantiles imply no hidden CDF/density/event/moments.

Gaussian NLL, exact Gaussian/empirical CRPS, pinball and Brier proper scores accompany
coverage/width, quantile frequency, PIT and sharpness diagnostics. Exact-sample
comparisons are descriptive and cannot select models. Bounded immutable lineage spans
probability state, completed point fit, fold, TRAIN feature/target evidence and later
truth only for evaluation. Additive store1.6/user_version=7 preserves all older rows,
DDL and metadata. Atomic failure, corruption, seeds, reversed insertion, restart and
concurrent correction are tested. No new runtime dependencies are introduced.

See [probabilistic forecasting](probabilistic-forecasting.md),
[distributions](forecast-distributions.md), [quantiles](quantile-forecasts.md),
[events](threshold-probabilities.md), [scores](proper-scoring-rules.md) and
[evaluation](probabilistic-evaluation.md).
AFRE-6 evaluates calibration diagnostics but does NOT fit calibration transformations.
AFRE-7 now implements a separate calibration layer above this frozen AFRE-6 boundary.

## AFRE-7 completed scope

CalibrationSpec reserves exact non-TEST samples under DEDICATED_CALIBRATION,
TRAIN_TAIL or ROLLING_PAST policies without redesigning AFRE-4 partitions.
Strict holdout enforces disjoint underlying model TRAIN. Exact raw forecasts must
have existed and been available at their historical origin; exact completed
verified truth must be known by calibration cutoff, including equality. A single
read snapshot freezes evidence, and atomic publication preserves every earlier
row, DDL, schema and metadata item. Later corrected truth requires explicit new
requests/state identity and leaves old bytes recoverable.

IDENTITY, fixed BINNED_PROBABILITY, deterministic PAV ISOTONIC_PROBABILITY,
Type-7 residual QUANTILE_OFFSET, exact-rank CONFORMAL_ABSOLUTE_RESIDUAL and
ROLLING_CONFORMAL are implemented. Event comparisons, levels, bins/ties/gap
interpolation/extrapolation, alpha, rolling count and numerical versions are pinned.
Independent quantile crossings fail closed. Finite-sample conformal ranks do not
interpolate or cap; insufficient scores reject. Coverage arguments rely on
exchangeability and can fail under nonstationary financial series.

Immutable states pin mappings/offsets/scores, fit sample, disjointness, clocks and
retrospective diagnostics. Application reads no truth, requires raw and state
availability at the origin cutoff and creates a separate CalibratedForecast.
Raw forecasts are unchanged. Only IDENTITY preserves a full calibrated distribution;
adjusted marginals/intervals do not invent a calibrated PDF/CDF. Independent later
evaluation keeps Brier/pinball and applicable proper scores, coverage error and
width separate, with exact-sample descriptive comparisons and explicit TEST reuse.

Bounded rolling drift uses fixed thresholds and STABLE/DEGRADED/INSUFFICIENT_DATA/
UNKNOWN states. It never refits or selects a model/calibrator. Canonical data-only
artifacts, verified indexes and one bounded calibration-to-upstream audit persist
under additive store1.7/user_version=8. Calibration schema stays1.0; engine0.8.0;
zero runtime dependencies. No portfolio, risk optimization or execution occurs.
Predictive metrics never establish trading profitability.

See [calibration](forecast-calibration.md), [partitions](calibration-partitions.md),
[probabilities](probability-calibration.md), [quantiles](quantile-calibration.md),
[conformal](conformal-calibration.md), [drift](calibration-drift.md) and
[completion report](AFRE_7_COMPLETION_REPORT.md).

**Next scope: AFRE-8 — Multi-Horizon Forecast Architecture.** Consistent declared
horizons, shared versus horizon-specific parameters, horizon dependencies/joint
identity, appropriate covariance and horizon-specific loss/evaluation remain
unimplemented. **Stop after AFRE-7.** Regime mixtures, model selection, ensembles,
portfolios, risk optimization and execution remain deferred/downstream.
