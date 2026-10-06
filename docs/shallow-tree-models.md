# Deterministic shallow regression trees

SHALLOW_REGRESSION_TREE is a research model fitted only on the exact admitted AFRE-4
TRAIN matrix. It uses squared error, target-mean leaves, exact node/leaf sample IDs and
counts, and explicit maximum depth1–4, minimum leaf count, maximum candidates1–64 and
minimum positive split improvement. It accepts raw original/interaction columns.
Model missingness is FAIL; no default missing branch, imputation or surrogate split.

For each feature, sort unique TRAIN values and form finite strictly interior midpoints
using a/2+b/2. Adjacent values without a representable interior midpoint produce no
candidate. If there are too many, choose equally spaced candidate indices (include
both endpoints when maximum>1; use the middle index when maximum=1). Candidate
selection uses inputs only. Work counts candidate×node sample evaluations and rejects
above the declared bound.

Choose minimum combined child SSE, then exact feature identity, then threshold.
Left branch is value≤threshold and right is value>threshold. Reject undersized leaves;
stop at depth, insufficient support, zero error or inadequate improvement. No held-out
pruning or automatic complexity selection exists. Prediction preserves every feature,
threshold, branch and final leaf in an immutable path diagnostic.

Trees are bounded research models, not broad AutoML. Monotonic/shape constraints,
post-hoc repair, forests, boosting, residual-tree composition, sequence models and
unrestricted growth are unsupported. Predictive metrics do not establish profitability.
