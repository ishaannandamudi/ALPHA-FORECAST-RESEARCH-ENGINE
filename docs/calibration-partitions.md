# Calibration partitions and causality

Calibration sample is fit data. CalibrationPartition adds explicit reservations
on unchanged AFRE-4 partitions; no CALIBRATION enum is injected into AFRE-4.
Spec pins reservation IDs, their full parent fold, half-open origin range, policy,
strict disjointness and optional rolling count. All reservation IDs must belong to
the same frozen dataset and rich target/horizon and meet the declared origin range.
No implicit reuse of VALIDATION is allowed.

DEDICATED_CALIBRATION authorizes an exact reserved subset of eligible TRAIN or
VALIDATION membership in its parent fold. TRAIN_TAIL requires parent TRAIN
membership plus an explicit tail origin boundary; a separately completed base
model fold must exclude the tail. ROLLING_PAST authorizes an explicit candidate
set and last-N-resolved rule. Sorting is by origin, stable instrument and sample
identity after cutoff eligibility; older resolved observations are excluded with
a recorded reason. Minimum count applies after selection.

Each request explicitly pins a raw ProbabilisticForecast and TargetVintage. Raw
forecasts require completed probabilistic fitting, exact raw model/spec and target,
a pinned sample with matching full origin, historical admissibility, and physical
raw availability at or before the origin availability cutoff. A forecast computed
later from historically knowable inputs is insufficient: provider/source time does
not prove that this raw forecast existed at its historical origin.

The reservation is checked against the exact underlying probabilistic TRAIN IDs.
Overlap metadata has DISJOINT_FROM_MODEL_TRAIN, OVERLAPS_MODEL_TRAIN and UNKNOWN
states. AFRE-7 supports only strict disjoint fits; overlap and unknown evidence are
not silently accepted. Underlying raw-fold TRAIN and TEST and raw IN_SAMPLE/TEST
scopes cannot supply calibration observations. TEST is denied even if another
parent reservation would relabel it. The base point model and probabilistic fold
remain the completed AFRE-5/6 causal scaffold.

Completed, verified, present finite truth must satisfy AFRE-2 known-by-cutoff
semantics, including `truth_available_time == cutoff`. Future/unverified truth
is explicitly excluded. Raw origins must precede cutoff. Fit completion/state
availability cannot be backdated. Historical reconstruction retains actual AFRE
computation clocks. Later corrected truth has a new source/target identity and
availability; explicit rebuilt requests produce a new state. Old states/forecasts
are never overwritten, and fixed references survive concurrent later insertion.

TEST truth may be joined only later for evaluation using the existing explicit
TEST identity/reuse record. TEST outcomes never set mappings, bins, offsets,
conformal scores, hyperparameters or methods. Independent evaluation also excludes
all actual calibration fit sample IDs. No automated model selection is implemented.
