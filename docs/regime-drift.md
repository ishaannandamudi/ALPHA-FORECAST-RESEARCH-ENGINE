# Descriptive regime drift

RegimeDriftDiagnostic pins two exact same-model evaluations with ordered disjoint
matched-truth origin windows and an explicit known cutoff/minimum count. It reports
state mean-probability differences, state weighted conditioned MAE differences when
both supports qualify, and known transition-origin frequency difference. Hard vectors
contribute one-hot frequencies; soft vectors remain probabilities. Error changes use
the evaluations' separately matched known truths. No unseen label enters diagnostics.

Fewer than the fixed minimum in either window produces INSUFFICIENT_DATA. Missing
state-error support or transition history yields an explicit null component. These
are descriptive shifts, without significance claims, calibrated degradation alarms,
automatic taxonomy changes, retraining, tuning, selection or promotion. Diagnostics
never write a fit/model artifact. AFRE-22 owns descriptive broader model health; AFRE-23
champion/challenger deployment evaluation remains distinct.

Changes may also reflect universe composition or matched-truth coverage differences
between windows. The diagnostic does not establish fixed-population attribution.
