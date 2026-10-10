# Alpha Forecast & Research Engine — master specification

Status: **AFRE-0–AFRE-20 complete**, engine 0.21.0,
foundation/feature-store/target/universe/dataset/model/probabilistic/calibration/multi-horizon/cross-sectional/event-conditioned schemas 1.0,
shared research store 1.20/user_version=21; regime-conditioned, mixture, nonlinear, sequence, uncertainty, orthogonalization, invariance, transaction-cost-research, multiple-testing and selection schemas 1.0.

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
| AFRE-20 | Hyperparameter & Model Selection Framework | Declared bounded TRAIN/VALIDATION model selection, separate from ensemble construction; nested tuning deferred |
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
these distinct phases. **Stop after AFRE-20.** AFRE-1 remains only the
Point-in-Time Feature Store. AFRE-6 implements explicit TRAIN-only uncertainty,
causal distributions and proper scoring. AFRE-7 adds separate causal calibration.
AFRE-8 composes exact horizons; AFRE-9 ranks exact same-origin securities;
AFRE-10 conditions exact events; AFRE-11 adds causal regime conditioning; AFRE-12
adds explicit expert composition; AFRE-13 adds explicit nonlinear interactions.
AFRE-14 adds causal ordered histories; AFRE-15 adds identified uncertainty metadata; AFRE-16 Signal Orthogonalization & Redundancy Analysis is complete; AFRE-17 Invariance & Stability Research is complete;
model selection, ensembles,
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

## AFRE-8 completed scope

HorizonSet pins exact typed elapsed/session/bar horizons and rich target definitions.
Comparable horizons sort semantically; mixed bases require explicit canonical order.
Independent and shared-feature architectures preserve separate models, folds,
cutoffs, uncertainty and calibration. The explicit shared linear backbone fits one
coefficient vector and horizon-specific intercepts on the exact all-horizon TRAIN
intersection, using fixed supplied weights and optional coefficient ridge penalty.
It currently requires raw features and exposes point outputs only. Shared learned
transforms and shared-output uncertainty require separate explicit extensions.

Immutable fit runs retain per-horizon TRAIN evidence, label cutoffs, folds,
preprocessing and underlying models. Bundles pin common full origin/security,
exact point/raw/calibrated layers, required availability and explicit COMPLETE/
PARTIAL/UNAVAILABLE entries. Expectations, medians, quantiles and horizon-qualified
events retain missing/unsupported values. Actual later composition clocks are not
backdated to the origin. Calibration stays horizon-specific; no pooling occurs.

Matched TRAIN residual covariance pins exact sample/target rows, mean centering,
N/N−1 denominator, ordered matrix and numerical tolerance. Symmetry, nonnegative
variances and bounded deterministic PSD validation fail closed without repair.
Dependence is descriptive; no full joint density, causal relationship, naive
return addition, quantile addition or proportional variance scaling is inferred.

Separate AFRE-5/6/7 evaluation respects each horizon's available truth and explicit
TEST access/reuse. Paired diagnostics use exact full-origin intersection; supplied
weighted MSE is descriptive and cannot select models. One bounded lineage spans
all earlier phases. Snapshot-frozen reads, immutable safe JSON, verified indexes
and additive transactional store1.8/user_version9 preserve earlier artifacts and
metadata. Engine 0.9.0, all public schemas 1.0, zero runtime dependencies.

See [multi-horizon forecasting](multi-horizon-forecasting.md),
[horizon sets](horizon-sets.md), [dependence](cross-horizon-dependence.md),
[consistency](multi-horizon-consistency.md), [evaluation](multi-horizon-evaluation.md),
[horizon calibration](horizon-specific-calibration.md) and
[completion report](AFRE_8_COMPLETION_REPORT.md).

## AFRE-9 completed scope

`afre.cross_sectional` preserves every AFRE-0 through AFRE-8 implementation and
public contract. Exact target/horizon, common ForecastOrigin information context,
PIT universe/eligibility, canonical stable-security order, model/provider/statistic,
ties, direction, missingness, peer normalization and group policy pin identities.
Frozen ranking construction is target-free; exclusions retain the full eligible grid.

Raw, population/sample z-score, explicitly scaled median/MAD and percentile outputs
remain separate from group demeaning and historical TRAIN preprocessing. Versioned
provider-neutral PIT memberships prevent current classifications projecting backward.
Relative linear models reuse AFRE-5 TRAIN matrices/QR and can demean only TRAIN targets.
All predictor/group inputs must be usable by origin; actual ranking clocks never backdate.

Point, expectation, median, quantile, threshold probability and external signals
have distinct exact score semantics. Provider-neutral external artifacts reuse all
six AFRE clocks and explicit quality states; qualified reconstruction requires exact
persisted evidence and locally approved attestors. Ordinary categorical/numeric
external state may become FeatureVintage data, without regime-conditioned models.
No AME package, private database, sibling layout, algorithms or execution state is coupled.
The downstream HFT integration system supplies external-engine adapters.

Later truth/evaluation pins exact vintage/origin/horizon and native TEST seals/reuse.
Pearson and declared tied-rank IC retain exact N, missingness and undefined states.
Top/bottom means, buckets, pooled group-demeaned IC and IC series are descriptive.
Stability distinguishes eligible-universe changes from ranked-set exclusions and
uses explicit intersection. Top-bottom spreads are not tradable portfolio returns;
no predictive metric proves profitability. No cross-horizon fused ranking exists.

Additive transactional 9→10 migration, immutable safe JSON, verified indexes and
bounded unified lineage preserve every prior row/DDL/metadata value. Engine 0.10.0,
store1.9/user_version10, cross-sectional schema 1.0; zero runtime dependencies.
See [rankings](cross-sectional-ranking.md), [normalization](cross-sectional-normalization.md),
[IC](information-coefficient.md), [groups](group-neutral-ranking.md),
[stability](rank-stability.md), [external integration](external-signal-integration.md),
[profile](cross-sectional-benchmark.md) and [completion report](AFRE_9_COMPLETION_REPORT.md).

## AFRE-10 completed scope

Provider-neutral EventReference reuses AFRE-1 six-clock AvailabilityEvidence and
SourceReference, retaining neutral EIE snapshot refs where supplied. Occurrence !=
publication != receipt != availability; same-time <= is accepted only with evidence.
Qualified historical delivery binds source/security and approved attestor while
retaining actual later reconstruction clocks. All reaction features retain their
own clocks through unchanged AFRE-9 ExternalSignal contracts. EIE remains an
external event producer; AME remains external. Downstream HFT integration owns adapters.

Exact full-origin ResearchSample/fold/PIT eligibility, explicit issuer/group refs,
class/subtype/scope, semantic attribute scales, elapsed windows, thresholds and
three overlap policies determine immutable observations. Four TRAIN-only families
fit independent target responses: class conditional mean, materiality/surprise
linear and declared event-feature linear. Class application shift is conditional
mean minus exact baseline forecast. No in-sample residual fiction, nonlinear
interactions or event extraction. All labels must be known at training cutoff.

Truth-free application preserves exact base point/raw probability bytes; optional
location translation preserves distribution shape/scale. Conditioned calibration
assessments report insufficient data or unavailable; unconditioned AFRE-7 states
cannot be silently reused. Actual forecast computation must lie within its origin
cutoff; late reconstruction of forecast computation is unsupported. CUSTOM scope
matching and session/bar event windows are unsupported metadata choices.

Matched baseline/conditioned later truth, explicit subgroup minimums/exclusions,
coverage and AFRE-9 same-origin IC preserve exact target/horizon and TEST access.
ALL_EVENTS_SEPARATE uses unit relation weights with distinct sample counts and
correlated repeated labels; evaluation/ranking requires one forecast per sample/security.
Separate horizons retain independent models, forecasts and evaluation. Conditioned
forecast != causal effect; event-conditioned ranking != portfolio construction.
Predictive metrics never prove trading profitability.

Atomic10→11 migration preserves all previous rows/DDL/metadata; new safe immutable
JSON, verified indexes, bounded lineage/replay and frozen reads resist subsequent
corrections. Engine 0.11.0, store1.10/user_version11, event-conditioned schema 1.0;
zero runtime dependencies. Earlier repository interfaces retain their original
snapshot metadata. See [forecasting](event-conditioned-forecasting.md),
[time](event-time-semantics.md), [windows](event-windows.md),
[attributes](event-surprise-materiality-novelty.md), [overlap](event-overlap.md),
[evaluation](event-conditioned-evaluation.md), [reactions](event-reaction-signals.md),
[profile](event-conditioned-benchmark.md) and [A–BC report](AFRE_10_COMPLETION_REPORT.md).

## AFRE-11 completed scope

Provider-neutral exact taxonomy/provider/state identities consume filtered hard or
ordered soft membership with six independent clocks. As-of != availability; late
receipt and unqualified archives remain unusable. Qualified reconstruction retains
actual later clocks. GLOBAL/MARKET/SECURITY/PIT SECTOR matching pins candidate/mapping
sets, maximum age and explicit latest/exact/fail selection, failing equal-time ambiguity.

Exact admitted TRAIN fits implement state target means, hard fitted-residual offsets
and supplied-probability-weighted residual offsets. In-sample fitted residual diagnostics
are explicitly separate from historical out-of-fold forecasts. Minimum distinct/effective
support and FAIL/USE_BASE/GLOBAL_OFFSET are declared; no hidden renormalization/gating.
Truth-free application preserves base bytes and optional raw probability shape/scale.
Exact event bases support target-mean location replacement in base→event→regime order.
Horizon-specific1h/1d fixtures share the same regime evidence but retain distinct models.

Causal supplied-history transitions retain full hard/soft vectors and observed elapsed
persistence, never future switches/full duration. Matched truth/point/proper scores,
state/kind/transition/horizon/event subgroups, explicit coverage and AFRE-9 IC retain TEST
seals/reuse. Soft support/entropy/low-confidence diagnostics remain descriptive. Global
calibration is incompatible; dedicated regime fitting remains unavailable. Known-window
drift describes probability/error/transition-frequency changes and never refits/selects.

Immutable bounded safe JSON, verified relational projections, transactional11→12 migration,
frozen reads and unified lineage preserve every earlier row/DDL/metadata item. Engine 0.12.0,
store1.11/user_version12, regime-conditioned schema 1.0, zero runtime dependencies. No direct
MCE/AME import, private database, sibling path, detector algorithm or executable plugin.
Downstream HFT integration supplies adapters. No predictive metric proves profitability.
See [forecasting](regime-conditioned-forecasting.md), [snapshots](regime-snapshots.md),
[membership](hard-soft-regimes.md), [transitions](regime-transitions.md),
[calibration](regime-conditioned-calibration.md), [drift](regime-drift.md),
[external integration](external-regime-integration.md),
[profile](regime-conditioned-benchmark.md) and [A–BK report](AFRE_11_COMPLETION_REPORT.md).

## AFRE-12 completed scope

Exact producer references remain distinct from origin-specific forecast bindings. Canonical
ExpertSet rejects semantic duplicates and requires identical rich target/horizon and output.
Native AFRE point/probability/event/regime experts and neutral microstructure/context/options/
generic experts retain individual source/model/availability/quality identities. Six-clock receipt
floors and locally approved historical-delivery evidence preserve actual later reconstruction.

Fixed normalized nonnegative weights and one declared TRAIN-only mean-SSE simplex fit are
separate contracts. Learned linear weights are constant across origins; gating features retain
causal audit evidence but contextual/softmax/neural gating is deferred. Native in-sample output
cannot stand in for historically admissible TRAIN predictions. Known TRAIN labels, exact fold/
cutoff, bounded solver work/convergence and immutable fit clocks define each gate artifact.

Truth-free application records complete expert presence/absence grids, original/effective
weights, exact contributions and final availability. FAIL, explicit drop/renormalization and
exact fallback preserve missing values as None. Actual computation must occur by origin;
backdated mixture computation is unsupported. Each horizon has a distinct set/gate; actual1h/1d
fixtures reuse AFRE-8 independent architecture and preserve identities.

Finite Gaussian/empirical component laws implement exact weighted CDF/events, expectation,
within-plus-between total variance and bounded CRPS. Gaussian-only NLL uses log-sum-exp;
empirical/mixed NLL is unsupported. Sparse quantile-only experts cannot supply an exact law/
expectation. All mixture quantiles remain explicitly unsupported; quantile averaging is invalid.
Component calibrators never become mixture calibrators. Dedicated assessment records
insufficient/unavailable/incompatible; fitted mixture calibration remains deferred.

Matched mixture/expert truth intersections, point/proper metrics, missing/gate/fallback cohorts,
AFRE-9 same-origin IC, weights/contributions/effective count/entropy and exact pair correlation/
disagreement remain descriptive. Ordered known-window drift never refits/prunes/selects.
TEST evidence seals evaluation and cannot fit, tune, select, calibrate or change any gate.
No expert independence, causal importance, portfolio interpretation or profitability is claimed.

Safe immutable JSON, verified indexes, transactional12→13 migration and bounded unified
lineage/frozen snapshots preserve every earlier row/DDL/metadata value and exact replay.
Engine 0.13.0, store1.12/user_version13, mixture schema 1.0; older schemas remain1.0.
Zero runtime dependencies; no direct AME/MCE/EIE/options implementation, sibling database,
private class, filesystem assumption, dynamic executable payload or runtime network.
Downstream HFT integration supplies real provider adapters. Expert weight != portfolio weight.
See [mixtures](mixture-of-experts.md), [contracts](expert-contracts.md), [gating](expert-gating.md),
[missingness](expert-missingness.md), [probabilities](probabilistic-mixtures.md),
[contributions](expert-contributions.md), [integration](external-expert-integration.md),
[profile](mixture-benchmark.md) and [A–BO report](AFRE_12_COMPLETION_REPORT.md).

## AFRE-13 completed scope

`afre.nonlinear` adds exact semantic scalar projections of unchanged AFRE-1 features,
AFRE-9 neutral signals, AFRE-10 security event attributes, AFRE-11 security filtered
regime membership and AFRE-12 causal expert/mixture outputs. Ordered source revisions
pin interaction values; commutative products normalize operand order. Unit algebra,
explicit missing/fallback/zero-denominator policies and finite outputs are mandatory.
Ten explicit transforms include bounded degree2/3 and fixed or TRAIN Type-7 quantile
piecewise knots with clamp extrapolation. No interaction search/automatic expansion.

Exact complete admitted AFRE-4 TRAIN samples fit knots, optional column standardization,
AFRE-5 QR linear coefficients with fixed ridge, or depth≤4 SSE regression trees.
Midpoint candidates are bounded by deterministic equal index spacing. Ties use SSE,
feature identity, threshold and left≤/right> semantics. Leaves retain exact TRAIN IDs,
counts/means/loss. Missing model columns fail; monotonic/shape constraints and splines
remain unsupported. TEST cannot choose interactions/splits/knots or fit any parameter.

Source availability respects receipt, qualified delivery and actual reconstruction
clocks. TRAIN matrix computation is explicitly later than sample origins; it does not
claim historical deployment. Feature-only held-out prediction checks source, transform,
model and actual computation against each full origin cutoff. No late forecast
reconstruction contract exists. Exact arithmetic contributions/tree paths are retained.
Optional compatible AFRE-6 location translation preserves shape/scale and recomputes
quantiles/events. Upstream calibration states are incompatible; dedicated fitting is
unavailable. Horizon-specific1h/1d fixtures remain independent.

Later exact matched point/proper scores, event/regime cohorts and AFRE-9 ranking/IC
retain pinned truth and TEST seals/reuse. Compatible-window coefficient sign/magnitude
and tree split recurrence are descriptive, never causal importance or automatic
pruning/model selection. Safe bounded canonical JSON, verified projections/links,
transactional13→14 migration, frozen snapshots and unified lineage preserve every
prior registry row, DDL, metadata and public schema. Engine 0.14.0, store1.13/user14,
nonlinear schema 1.0 and zero runtime dependencies. No direct external-engine dependency,
sequence modeling, portfolio, risk optimization, execution or profitability claims.

See [interactions](nonlinear-feature-interactions.md), [definitions](interaction-definitions.md),
[transforms](nonlinear-transforms.md), [trees](shallow-tree-models.md),
[stability](interaction-stability.md), [cross-domain](cross-domain-interactions.md),
[evaluation](nonlinear-evaluation.md), [profile](nonlinear-benchmark.md)
and [A–BI report](AFRE_13_COMPLETION_REPORT.md).

## AFRE-14 completed scope

Causal sequences accept ordinary/event/FILTERED-regime/neutral microstructure/context/options,
expert/mixture and nonlinear histories through existing provider-neutral contracts. Exact
source definitions, units, observation time, final availability and revision fingerprints are
pinned. Live source availability cannot precede AFRE receipt; qualified historical delivery
requires approved evidence and preserves actual later ingestion/computation clocks.

Fixed-count and exact elapsed UTC windows apply availability filtering before deterministic
revision resolution. Candidate rosters cannot precede candidate availability at construction.
Exact timestamp-union alignment preserves per-feature masks, left/right
masked padding, no silent filling and four completeness states. Irregular deltas, origin ages
and ordinal positions are explicit. Session windows and grid interpolation are unsupported.
TRAIN transforms bind the complete exact admitted fold/sample set; population standardization
uses unmasked TRAIN tokens only and rejects zero scales. Known target vintages are confined to
TRAIN fitting or separate later evaluation. Held-out feature/label changes never choose settings.

Fixed exponential decay and stable diagonal per-observation state dynamics feed a bounded
AFRE-5 QR readout with optional supplied ridge. Zero initial state, masked update skips,
exact contributions and state trajectories are pinned; no nonlinear recurrence/attention,
bidirectional future context, learned dynamics or broad model search is implemented.
Feature-only VALIDATION/TEST application rejects later snapshots/models/computation clocks.
Compatible AFRE-6 law shifts preserve shape/scale; upstream calibrators are incompatible and
dedicated sequence calibration fitting is unavailable. AFRE-9 ranking, independent actual1h/1d
identities, exact matched truth/proper scores, event/regime cohorts, TEST seals/reuse, descriptive
coverage/coefficient ranges and bounded unified lineage are supported without auto-refit.

Transactional14→15 migration is additive: all previous rows, DDL, metadata and public schemas
remain unchanged. Engine 0.15.0, sequence schema 1.0, store1.14/user_version15, zero runtime
dependencies. Strict safe canonical persistence verifies hashes, family/schema, projections,
links and semantic replay. Limits128timestamps/16features/2000TRAINrows/2mworkcells/8MiB,
plus explicit observation/forecast/audit counts/depth, fail closed. Provider timestamp honesty
and upstream causal derivation remain trust boundaries; contracts do not authenticate them.

See [sequence architecture](temporal-sequence-models.md), [windows](sequence-windows.md),
[masks](sequence-masking.md), [time encoding](sequence-time-encoding.md),
[TRAIN fitting](causal-sequence-training.md), [families](sequence-model-families.md),
[external sources](external-sequence-integration.md), [evaluation](sequence-evaluation.md),
[profile](sequence-benchmark.md) and [A–BT report](AFRE_14_COMPLETION_REPORT.md).

## AFRE-15 completed scope

Exact Gaussian/finite empirical predictive variance, exact finite-mixture within/between
closure and explicit compatible remainder; non-additive model/expert spread, supplied regime
entropy/state-mean ambiguity and event-conditioned/base proxy. Quality states carry no invented
variance or penalty. Conservative unpenalized full-rank AFRE-5/13/14 readout covariance pins
TRAIN-only fixed-design iid homoskedastic correct-model assumptions, SSE/(N−rank), intercept,
pivoted QR condition/rank policy and prediction xᵀCov(beta)x. Ridge/tree/dynamics/selection
uncertainty remains unsupported. Aleatoric != epistemic; disagreement != epistemic automatically.
Calibration measures reliability, not causal uncertainty-source attribution.

Causal VALIDATION/TEST construction blocks truth and TRAIN-response reads. Availability is
at least actual computation and all sources; no reconstruction/backdating permission is added.
Exact-law or compatible stored-calibration intervals, separate coverage/sharpness/proper scores,
minimum-count cohorts, matched truth comparison, ordinal buckets/error correlation and known-window
drift are descriptive with no auto-refit/selection. Every decomposition is horizon-specific;
actual1h/1d evidence remains independent, no joint law or time scaling is invented.

Immutable canonical data-only specs/components/decompositions/intervals/covariance/evaluations/
comparison/drift/audits have fixed indexes and bounded unified lineage. Transactional15→16 migration
adds uncertainty store1.15/user_version16; engine0.16.0, uncertainty schema 1.0, all earlier schemas 1.0,
zero runtime dependencies. Earlier public contracts/source/tests remain unchanged.
See [uncertainty architecture](forecast-uncertainty-decomposition.md), [identifiability](uncertainty-identifiability.md),
[parameter methods](parameter-uncertainty.md), [evaluation](uncertainty-evaluation.md),
[profile](uncertainty-benchmark.md) and [A–BM report](AFRE_15_COMPLETION_REPORT.md).

## AFRE-16 completed scope

Supplied exact candidate/reference semantic/model/version/unit identities bind source artifacts to
admitted research samples/full origins. Ordinary features, neutral external sources, event/regime,
expert/mixture, nonlinear/sequence outputs and explicitly numerical uncertainty diagnostics are
supported without direct external-engine dependencies. Provider publication is not AFRE receipt.
Qualified reconstructed bindings require caller-approved exact historical-delivery evidence and
retain later actual receipt/ingestion/computation clocks.

TRAIN-only deterministic pivoted QR projects the candidate response on references, with explicit
intercept, NONE/TRAIN_STANDARDIZE preprocessing, equal-row weights, minimum support and stable
rank/condition policy. Frozen coefficients/preprocessing, exact TRAIN samples/candidate values,
VIF and common-intersection correlation matrices are persisted. Deficient/ill-conditioned designs
fail; no hidden imputation, pseudo-inverse, regularization or pruning occurs. Target-free residual
construction requires feature-only reads, causal sources/model and actual computation no later
than the full origin cutoff. Residuals preserve candidate units and explicit missing states.

Held-out R²/MSE and population residual/candidate variance ratios remain distinct. Separately fixed
TRAIN target readouts compare references-only with references plus raw candidate/residual on the
same exact later truth intersection, with augmented-minus-base metrics and explicit TEST seals.
Partial Pearson and rank-of-linear-residual association use separately TRAIN-fitted nuisance
transforms. Orthogonal != independent; redundancy depends on the declared metric, sample and set.
No significance, uniqueness, causal novelty or profitability is inferred.

TEMPORAL_PANEL and CROSS_SECTIONAL_HISTORICAL are implemented. Historical cross-sectional fits
pin complete eligible AFRE-3/9 TRAIN grids and apply within later origins. Explicit residual feature
export and AFRE-9 ranking retain exact target/horizon, universe and historical group memberships.
One full universe/origin context per timestamp is required for cross-sectional fitting, evaluation
and ranking.
Actual1h/1d analyses are separate. Caller-supplied independent candidates and ordered disjoint-window
coefficient/correlation/variance-ratio summaries never search references, select survivors, refit,
promote or mutate downstream models. Per-origin fits, lag search, basis construction and a new
within-group projection estimator are unsupported.

Historical AFRE-16 checkpoint: Engine 0.17.0, orthogonalization schema 1.0, store1.16/user_version17, all earlier schemas 1.0 and zero
runtime dependencies. Transactional16→17 migration preserves prior rows/DDL/metadata. Safe canonical
immutable artifacts verify family/schema/hash, indexed projections/links and semantic replay.
Frozen snapshots isolate concurrent candidate/reference/projection/target corrections. Bounds cover
references/candidates, rows, matrix/work cells, family counts, windows, payload and lineage bytes/nodes/depth.

See [architecture](signal-orthogonalization.md), [redundancy](signal-redundancy.md),
[partial association](partial-correlation.md), [construction](orthogonal-signal-construction.md),
[collinearity](collinearity-diagnostics.md), [incremental value](incremental-signal-value.md),
[cross-sectional](cross-sectional-redundancy.md), [temporal](temporal-redundancy.md),
[profile](orthogonalization-profile.json) and [A–BP report](AFRE_16_COMPLETION_REPORT.md).

**Next scope: AFRE-21 — Ensemble & Signal Fusion.**
Fixed ensembles, TRAIN/VALIDATION-safe learned weights, stacking where justified,
point forecast fusion, probabilistic fusion, signal fusion and diversity-aware diagnostics.
Model-health automation remains AFRE-22. **Stop after AFRE-20.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.

## AFRE-17 completed scope

Historical AFRE-17 checkpoint: engine 0.18.0, invariance/stability schema 1.0,
shared store 1.17/SQLite user_version=18; every earlier public schema remains 1.0.
The roadmap freezes 26 distinct phases, AFRE-0 through AFRE-25.

AFRE-17 adds [declared environment stability](invariance-stability-research.md), exact PIT
memberships, native point/probabilistic/calibration/IC metrics, explicit intersections and
minimum counts, supplied frozen parameter diagnostics, feature-distribution distances and
separate error degradation. Stability != causal invariance proof. No significance or trading
profitability claim, TEST-driven environment selection, auto-refit, auto-prune or promotion.

Run `.venv311/bin/python -m examples.invariance_demo` for the 37-step offline demo and
`.venv311/bin/python -m benchmarks.invariance_profile` for the bounded profile. See the
[A–BW completion report](AFRE_17_COMPLETION_REPORT.md) and [profile](invariance-profile.json).

**Next scope: AFRE-21 — Ensemble & Signal Fusion.**
Fixed ensembles, TRAIN/VALIDATION-safe learned weights, stacking where justified,
point forecast fusion, probabilistic fusion, signal fusion and diversity-aware diagnostics.
Model-health automation remains AFRE-22. **Stop after AFRE-20.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.
## Historical AFRE-18 completed scope

AFRE-0 through AFRE-18 are complete. Engine 0.19.0, transaction-cost-research schema 1.0,
shared store 1.18/SQLite user_version=19; all earlier schemas remain 1.0 and runtime
dependencies remain empty. The frozen roadmap has 26 distinct phases, AFRE-0 through AFRE-25.

AFRE-18 adds explicit bounded per-security exposure paths, initial policies, absolute-change
turnover, six-clock provider-neutral spread/fee/slippage/impact inputs, historical-causal
and ex-post timing, matched arithmetic gross/cost/net contributions, explicit missing/fallback
policy, embedded-category protection, algebraic break-even and supplied sensitivity grids.
Native forecasts, residual signals, uncertainty metadata, PIT cohorts and actual1h/1d
assessments remain distinct. No execution optimization, fill, capacity, profitability,
portfolio performance, automatic selection or TEST-driven tuning claim is made.

See [cost research](transaction-cost-aware-research.md),
[scenarios](cost-scenarios.md), [exposure rules](research-exposure-rules.md),
[spread/fees/slippage](spread-fee-slippage.md), [impact](market-impact-research.md),
[turnover](turnover-diagnostics.md), [break-even](break-even-cost.md),
[sensitivity](cost-sensitivity.md), [measured profile](costs-profile.json) and
[the A–BS report / 50 gates](AFRE_18_COMPLETION_REPORT.md).
Run `PYTHONPATH=src:. .venv311/bin/python -m examples.costs_demo` for the checked 40-step
offline demo and `PYTHONPATH=src:. .venv311/bin/python -m benchmarks.costs_profile` for the profile.

**Next scope: AFRE-21 — Ensemble & Signal Fusion.**
Fixed ensembles, TRAIN/VALIDATION-safe learned weights, stacking where justified,
point forecast fusion, probabilistic fusion, signal fusion and diversity-aware diagnostics.
Model-health automation remains AFRE-22. **Stop after AFRE-20.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.

## Historical AFRE-19 completed scope

AFRE-0 through AFRE-19 are complete. Engine 0.20.0; multiple-testing schema 1.0;
shared store 1.19/SQLite user_version=20. Earlier public schemas remain 1.0.
Earlier completed-scope version statements above are historical release checkpoints.

Immutable planned opportunities and their separate completions retain exact source,
hypothesis, target/horizon, fold, environment, cost, preprocessing and inspected-choice
identities. Every frozen family retains failed, unavailable and missing attempts in its
full denominator. Conditional exact sign tests require explicit caller-attested
independence, fair nonzero signs, nonoverlapping native labels and exact pairing.
Bonferroni/Holm control nominal FWER; BH requires independence/PRDS; BY supports
arbitrary dependence of valid marginal p-values. The level and every reported method
are fixed in the family before the held-out boundary. Open, adaptive, unknown and
retrospective analyses carry interpretation limits and make no final discovery claim.

P-value != effect size. Median effects are separate; CI/SE, normal/correlation inference
and Sharpe/generic deflation are unsupported. Corrections do not eliminate data snooping,
leakage, adaptivity or nonstationarity. Significance != causality; significance !=
profitability. Selection events describe caller-supplied outcomes and retain candidate
sets, ordering/ties and TEST involvement. No model selection, promotion, pruning or
automatic follow-up hypotheses occur. Registry snapshots contain all visible registered
opportunities; exact TEST seals, reuse thresholds and untracked native history remain
explicit. New evidence creates new IDs while frozen old results remain byte-identical.

See [controls](multiple-testing-controls.md), [registry](research-trial-registry.md), [families](hypothesis-families.md), [FWER](fwer-controls.md), [FDR](fdr-controls.md), [TEST reuse](test-reuse.md), [selection](selection-bias.md), [overfitting](research-overfitting.md), [profile](multiple-testing-profile.json) and [A–BT report](AFRE_19_COMPLETION_REPORT.md).

**Next scope: AFRE-21 — Ensemble & Signal Fusion.**
Fixed ensembles, TRAIN/VALIDATION-safe learned weights, stacking where justified,
point forecast fusion, probabilistic fusion, signal fusion and diversity-aware diagnostics.
Model-health automation remains AFRE-22. **Stop after AFRE-20.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.

## AFRE-20 completed boundary

AFRE-20 is the [declared model selection framework](model-selection-framework.md).
Engine 0.21.0; selection schema 1.0; shared store 1.20/SQLite user_version=21;
earlier public schemas remain 1.0 and runtime dependencies remain empty.
TRAIN fits; VALIDATION selects; TEST evaluates only later under native seals and
AFRE-19 reuse accounting. Selection references the immutable TRAIN-fitted model.

Complete bounded Cartesian grids, explicit native recipes, exact request cutoffs,
deterministic fingerprint ties, failure/incompatibility/minimum-support states and
complete candidate registries preserve the inspected opportunity denominator. Native
families AFRE-5/6/10/11/13/14 are integrated. An explicit causal AFRE-16 residual feature
can enter the native nonlinear input; earlier TEST rows cannot become selection rows.
MIN_MSE, MIN_MAE, MAX_R2, Gaussian/empirical CRPS and Gaussian NLL are supported.
IC/rank IC, AFRE-18 cost selection, automatic calibration and AFRE-12 orchestration
are deferred. Native AFRE-19 SelectionEvent is emitted only on exact metric/direction/
ordering compatibility; otherwise the full AFRE-20 decision/trial pool stays explicit.

Frozen snapshots, additive transactional20→21 migration, immutable indexed storage,
source/label correction identities, bounded audits, hash-seed/order/restart replay and
real second-writer regressions preserve old result bytes. There is no hidden adaptive
search, TEST tuning, validation-based early stopping, automatic final refit, ensemble
fusion, model promotion or production deployment. Independent walk-forward/horizon
calls are supported; nested, coupled, random/Bayesian/continuous and partial search
are unsupported. VALIDATION selection does not prove generalization or profitability.

See [spaces](search-spaces.md), [registry](candidate-registry.md),
[validation](validation-selection.md), [budgets](resource-budgets.md),
[families/comparisons](model-family-comparison.md),
[TEST isolation](test-isolation-selection.md),
[reproducibility](selection-reproducibility.md),
[measured profile](selection-profile.json) and
[A–CB report](AFRE_20_COMPLETION_REPORT.md).
Run `PYTHONPATH=src:. .venv311/bin/python -m examples.selection_demo` for 35 verified
steps and `PYTHONPATH=src:. .venv311/bin/python -m benchmarks.selection_profile` for
separate bounded timing/storage measurements. There is no production SLA.

**Next scope: AFRE-21 — Ensemble & Signal Fusion.**
Fixed ensembles, TRAIN/VALIDATION-safe learned weights, stacking where justified,
point forecast fusion, probabilistic fusion, signal fusion and diversity-aware diagnostics.
Model-health automation remains AFRE-22. **Stop after AFRE-20.** Portfolio construction,
risk optimization and execution remain downstream projects after AFRE.
