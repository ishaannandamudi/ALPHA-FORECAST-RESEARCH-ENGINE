# Calibration drift diagnostics

AFRE-7 diagnoses calibration drift over bounded historical evaluation windows.
It does not implement AFRE-22 model health, auto-refit, promotion or model selection.
CalibrationDriftSpec pins metric, fixed threshold, minimum pair count, number of
trailing evaluations and implementation version. CalibrationDriftDiagnostics pins
state, ordered evaluation IDs and exact windows/cutoffs/counts/values/statuses.

Evaluations order by cutoff then identity and must share calibration state, target,
protocol and scope. Each window uses up to N trailing evaluation artifacts, and
recomputes diagnostic summaries on their exact stored truth and forecast outputs.
It reads no newly inserted target truth. A window with repeated sample identities
rejects, so rerunning one evaluation cannot inflate evidence by counting the same
truth twice. Empty evaluations do not create fabricated diagnostic observations.

Supported metrics are mean per-event Brier, mean per-event fixed-bin ECE,
maximum absolute quantile frequency gap, and absolute interval coverage gap.
All use the same calibration definitions as evaluation. A count below the pinned
minimum produces INSUFFICIENT_DATA; an absent applicable metric produces UNKNOWN.
For sufficient supported evidence, `value > threshold` means DEGRADED, otherwise
STABLE (threshold equality is stable). There is no probabilistic significance or
multiple-testing claim attached to these diagnostic flags.

Diagnostics persist new immutable records only. They do not mutate calibration
state, create a fit, change a cutoff, tune a threshold or ingest TEST outcomes into
fitting. Deliberate recalibration is a separate explicit fit on a legitimate
reservation. TEST evaluation history remains TEST history; a drift warning never
turns it into fit data. Width/sharpness and proper-score changes remain separate
from empirical calibration frequencies.
