# Matched event-conditioned evaluation

Application is truth-free; later evaluation uses exact ResearchSample target vintage
and full TargetDefinition/origin, known by an explicit later cutoff. One conditioned
model/target/horizon/partition and unique samples are required. Unavailable truths
produce explicit exclusions. Baseline and conditioned forecasts share precisely the
same matched pairs, never two independently selected populations. Deltas mean
conditioned metric minus baseline metric. Proper scores use the exact raw probability
and its shape-preserving conditioned view; the view is not published as a native
AFRE-6 forecast.

Groups describe affected/unaffected, class, configured materiality/novelty/surprise,
age, horizon and overlap. Declared sorted cutpoints use bisect_right: equality falls
in the upper bucket. Groups below the minimum have counts and insufficient-data
state but no invented metrics. Coverage is affected forecasts / all supplied eligible
forecasts, independently of truth exclusions. No causal-effect interpretation.

AFRE-9 consumes neutral scores derived from exact conditioned forecasts. Full common
origin context, target/horizon, PIT universe, exact group vintages and a single
conditioned-model statistic remain pinned. A wrapper retains affected/unaffected
identities. Event IC uses the same matched truth vintage set and existing AFRE-9
ranking/tie/normalization rules. Each horizon is fitted/evaluated independently;
no pooled event model, fused rank or joint distribution exists.

Native TEST requires an explicit evaluation identity and persisted TestEvaluation
access record from the exact fold/cutoff. Exact reuse is idempotent; conflicting
reuse fails. TRAIN and TEST never fit conditioned calibration. Inspecting many event
subgroups does not solve multiple testing; AFRE-19 provides explicit trial-family accounting and conservative supported tests; see [controls](multiple-testing-controls.md).
Ranking != portfolio construction; top/bottom and IC are predictive diagnostics,
not tradable strategy returns or profitability evidence.
