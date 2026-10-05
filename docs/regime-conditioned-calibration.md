# Regime-conditioned calibration boundary

RegimeCalibrationAssessment exposes SUPPORTED, INSUFFICIENT_DATA, UNAVAILABLE and
INCOMPATIBLE. SUPPORTED is reserved; no regime calibrator is fitted in AFRE-11.
The artifact rejects a false supported claim. Too few independent observations
reports INSUFFICIENT_DATA; enough exact observations reports UNAVAILABLE because
conditioned calibration fitting is unimplemented. A supplied existing AFRE-7 global
state is explicitly INCOMPATIBLE with new regime semantics and is never applied.

Assessment requires exact same model/membership (including the full soft vector),
unique non-TRAIN/non-TEST VALIDATION samples, origin-admissible forecasts and truth
known at cutoff. Empty evidence can assess scarcity. Actual calibration diagnostics
and proper scores remain available through matched evaluation; they do not create a
calibrator. TEST never fits or assesses calibration observations. Future dedicated
calibration must follow AFRE-7 reservation, availability and compatibility rules.
