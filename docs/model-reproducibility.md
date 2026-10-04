# Model persistence, replay and bounds

ModelRepository upgrades shared research store 1.4/user_version=5 to
1.5/user_version=6 transactionally. Five model artifact/index tables add specs,
fit lookup, forecast origin/security/scope and evaluation partition/cutoff indexes.
All earlier SQL, payloads and creation metadata remain byte-identical. Injected
migration failure rolls back; unknown future versions and altered layouts fail.
Strict earlier repository interfaces keep their earlier version boundary.

Specs, matrices, fit inputs/runs, diagnostics, coefficient artifacts, predictions,
evaluations, comparisons and audits are immutable safe canonical JSON. The closed
decoder selects only statically registered data classes/enums. No pickle, joblib,
executable import, provider-selected code/path, shell or network is used. Reads
verify family/schema/hash and independent relational indexes; whole-store audit
rejects orphan/wrong-family indexes and recomputes matrix/solver/evaluation semantics.

ModelLineageAudit traces model → exact run/input/matrix → TRAIN samples → frozen
features/vintages/preprocessing and admitted labels. Prediction audits add its exact
feature input without joining held-out truth. Evaluation audits add the explicit
later truth evidence. The dataset's complete grid hash is pinned while only explicit
TRAIN rows are expanded for fitting. A single depth/node/byte budget includes both
model and upstream lineage. Cycles, overflow and unresolved references fail.

Defaults bound 50,000 samples, 64 features (declared ceiling 128), 65 coefficients,
10,000 iterations, 50,000 predictions, 10,000 stored evaluations/history results,
4,000,000 dense cells, 100,000 audit nodes, depth 64 and 8 MiB serialized bytes.
The closed decoder's hard ceiling is 16 MiB. Larger declared bounded audit budgets
may be supplied up to that ceiling. No silent truncation or implicit streaming occurs.

Four Python hash seeds (0/1/42/random), reversed upstream/request/prediction insertion
and restart produce identical semantic artifacts on the supported Python/platform
arithmetic environment. Operation order is fixed; universal cross-platform bit
identity is not promised. Fit timings are outside identities. Backdated corrections
change new dataset/spec/fit lineage while leaving old bytes unchanged. A real second
connection can insert during the pinned fit; frozen selections cannot change.

The [profile](../benchmarks/statistical_models.py) measures a bounded multi-fold registry
pipeline separately from a 4,000-row/16-feature known-coefficient numerical workload.
It reports matrix/solver/persistence, prediction, evaluation, audits, restart, disk,
coefficient error and ridge stationarity. The pipeline has fewer TRAIN rows because
existing AFRE-1 embedded universe provenance dominates scaling; the numerical workload
does not claim equivalent end-to-end registry throughput. All measurements are local
synthetic evidence with no production SLA.

AFRE-6's ProbabilisticRepository extends this store additively to 1.6/user_version=7.
All AFRE-5 rows, DDL, metadata and contracts remain intact. ModelRepository retains
its strict 1.5 interface and historical 0.6.0 snapshot metadata. Probability specs,
TRAIN state, forecasts, evaluations and bounded lineage replay independently; see
[probabilistic persistence](probabilistic-evaluation.md). AFRE-6 evaluates calibration
diagnostics but does NOT fit calibration transformations. AFRE-7 owns calibration.
