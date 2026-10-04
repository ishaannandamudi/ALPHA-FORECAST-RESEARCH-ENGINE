# Feature computation DAG

`FeatureComputationGraph` contains exact registered definitions with foundation
feature-definition dependency edges. It rejects unknown/self dependencies,
duplicate nodes/edges, unsupported cross-scope edges and cycles. A heap produces
a deterministic topological order by foundation feature ID. Definition namespaces
and typed feature-only references exclude target/result nodes.

`FeatureComputationSpec` pins output, ordered inputs, static transformation ID,
transformation and implementation versions, parameters, minimum observations,
missing-input policy, window basis/count and optional supplied normalization
state. Parameters must agree with the output definition. Input order is semantic
for DIFFERENCE. Changes in bound logic require a new definition revision; changing
normalization state changes spec/result identity independently.

The trusted local registry implements IDENTITY, DIFFERENCE, PERCENT_CHANGE,
LOG_RETURN, ROLLING_MEAN, sample ROLLING_STDDEV and STANDARDIZE using supplied
mean/stddev. Units must agree for identity/difference/mean/stddev; returns and
standardized results declare ratio. Unsupported implicit conversions fail.
There are no dynamic plugins, Python callables or executable source strings.

LATEST_VALUES uses one admissible nonstale PRESENT value per declared input.
ELAPSED_LOOKBACK uses effective observations in **(T-lookback, T]**, whose final
availability is <= the origin cutoff, retaining each observation's exact as-of
revision. OBSERVATION_COUNT trims that causal elapsed window to the last declared
count; it does not silently expand the declared lookback. Minimum observations
and REJECT/PROPAGATE missing policy are explicit. Rolling history retains explicit
missing observations; absent input does not become zero. Rolling history uses
explicit observation states and declared lookback; current-value freshness is
applied to latest-value lookup.

Computation pins all inputs/state and persists output and
`FeatureComputationReceipt` atomically inside one writer snapshot. The receipt
retains spec, forecast origin, exact input/output vintage IDs, processing bound
and normalization identity. Final output availability >= every dependency and
state availability; actual computation >= its information cutoff. A qualified
reconstruction may establish a historical processing bound while retaining later
physical clocks. No automatic replay/backdating is performed.

`lineage` follows source parents, completed market bars, input vintages, receipts,
predecessors, computation specs and normalization fit observations. Depth, nodes
and serialized bytes are bounded; active and completed traversal nodes both count.
Cycles, unresolved references, wrong reference families and target provenance
fail closed. Normal lookup validates selected records/indexes and receipt
existence; append and explicit deep audit perform recursive lineage validation.
The database is assumed immutable after successful validation; an administrator
who rewrites internally consistent content requires external authentication controls.
