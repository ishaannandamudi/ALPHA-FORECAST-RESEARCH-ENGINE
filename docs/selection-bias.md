# Descriptive selection events

SelectionEvent records a caller-supplied complete candidate set and selected identities,
metric, MAX_METRIC/MIN_ERROR/TOP_K/DECLARED_THRESHOLD rule, orientation, k/threshold,
canonical ordering/ties, cutoff and TEST involvement. AFRE validates the supplied outcome;
it does not search for, return, promote or prune a winning model.

Candidates must have exactly compatible dataset/fold, target/horizon, metric/null and
planned sample grid. Observed sample/truth sets must match; no silent union of disjoint
universes or truth vintages. Failed candidates remain visible with unavailable effects.
Available candidates order by oriented descriptive effect and immutable trial identity;
unavailable candidates remain at the end. A forged selection, ordering or TEST flag rejects.

SelectionBiasDiagnostic retains the full candidate count and values, winner metric,
median, winner-minus-median, winner-minus-runner-up, exact adjusted evidence from one
family/correction and TEST use count. Missing candidate metrics make full-pool spread
statistics unavailable rather than silently calculating a smaller-pool median. The
native demo verifies complete-pool spreads independently. No winner's-curse shrinkage,
selection-adjusted CI or claim that these descriptive gaps repair selection bias.

This phase is descriptive accounting. AFRE20 owns candidate/search spaces and model
selection; AFRE21 owns ensemble fusion. See [overfitting](research-overfitting.md).
