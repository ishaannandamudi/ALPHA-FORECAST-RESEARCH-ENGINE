# Multi-horizon evaluation

Evaluation joins truth later at an explicit cutoff, separately for every horizon.
It reuses AFRE-5 point metrics, AFRE-6 proper scores and AFRE-7 calibrated scoring
and diagnostics. CalibrationEvaluation references retain full reliability and
coverage diagnostics. The shared point layer reuses the AFRE-5 scaffold evaluation
for exact truth/fold/TEST evidence and recomputes point metrics with its own values;
its scaffold metrics are not reported as shared-model accuracy.

Every horizon reports evaluated full-origin identities and a missing count for
absent bundle entries or truth unavailable/unverified at cutoff. There is no
silent union of samples. Cross-horizon paired point diagnostics use the exact
intersection and retain separately recomputed metrics on that common set. The
per-horizon metrics can have different sample counts; the matched metrics make
comparisons on equal observations explicit.

The optional declared weighted MSE is sum(weight×per-horizon MSE)/sum(weights).
It is descriptive aggregation of each horizon's own admitted sample. If a
positive-weight horizon has no available MSE, the aggregate is None; its weight
is never silently redistributed. Weights live in immutable model/evaluation
identity and cannot be learned or used for architecture/model selection.

Each TEST horizon requires a supplied access identity and its own AFRE-4
TestEvaluation record. Exact repeats are idempotent. New access records reference
prior access for that fold; reusing an identity with changed cutoff or evidence
rejects. Point/probability/calibration evaluations share that exact seal for a
horizon. Empty horizons cannot invent TEST access. Multi-horizon evaluation
publishes all per-horizon evidence and the aggregate in one transaction.

Metrics and horizon-to-horizon performance differences provide predictive research
evidence. They do not establish trading profitability, portfolio allocations or
execution decisions. Multiple-testing governance remains explicit future AFRE-19;
model selection belongs to AFRE-20.
