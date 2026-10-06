# Explicit interaction identities

ScalarFeatureDefinition pins kind, ordered semantic source key, selector and exact unit.
ScalarInput adds exact source artifact/revision, full ForecastOrigin, scalar or explicit
None, final availability and locally approved delivery attestors. Supported sources:
security FeatureVintage, ExternalSignal, security EventReference attributes, security
FILTERED RegimeSnapshot membership, ExpertForecastBinding and MixtureForecast point.
Native in-sample forecasts cannot masquerade as causal expert bindings.

InteractionDefinition pins semantic name, ordered exact input definitions, closed
transform, structured parameters, output name/unit, FAIL/PROPAGATE_MISSING/DECLARED_FALLBACK,
explicit fallback value, max-input/state/actual-computation policy and implementation.
PRODUCT/ABS_DIFFERENCE canonicalize operand order; ratio/difference preserve it.
Products use canonical ordered unit multiplication, ratios divide units (equal units
produce1), differences require equal units, powers retain explicit degree and signed
log requires unit1. Piecewise ordinates retain the input unit.

InteractionSet canonicalizes interaction IDs, rejects duplicate semantics and output
names, pins target/horizon and maximum128 interactions. No implicit full polynomial
expansion or specification choice from held-out performance exists.

NonlinearModelSpec pins set, rich target/horizon, originals, family, fold/cutoff,
NONE/STANDARDIZE preprocessing, FAIL model missingness, optional tree, fixed ridge,
QR tolerance/condition ceiling, explicit seed and approved historical-delivery attestors.
A seed is identity-bearing; current algorithms contain no stochastic choice.
Every model column has exact identity/order. Original columns precede interactions.

Fitted transform/model artifacts retain exact TRAIN inputs/sample IDs, fold/cutoff,
fit start/completion/final availability, fitted knots/centers/scales/coefficients or
tree nodes, diagnostics and canonical fingerprint. No opaque executable serialization.
