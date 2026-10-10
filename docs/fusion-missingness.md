# Explicit missing-source policies

FAIL returns an immutable unavailable forecast when a declared source is absent or lacks a scalar value. It does not delete the spec's source set. Incompatible, corrupt or temporally invalid inputs fail closed rather than being treated as missing.

DROP_AND_RENORMALIZE is allowed only for a fixed nonnegative SIMPLEX rule with no intercept. Surviving weights divide by their positive sum and are recorded in contributions. With no positive survivor, output is unavailable. Signed weights and learned QR weights cannot use this policy. Probability laws remain explicit exact mixtures after valid dropping.

USE_DECLARED_FALLBACK pins a separate compatible source reference in the spec. When primary columns are incomplete, the caller must supply that exact sample/origin fallback observation. Its value/law is used with weight one and intercept zero. No source search occurs. An unavailable fallback is rejected explicitly. TRAIN-standardized fallback is unsupported because the fallback normalization semantics would require a separate explicit bridge.

Learned fusion never silently deletes a column, substitutes zero or refits weights. It can fail or use a declared compatible fallback. Every forecast records observations, actual contributor weights, status, fallback evidence and the intercept actually used. Availability includes the fitted artifact, computation and every actually used output.
