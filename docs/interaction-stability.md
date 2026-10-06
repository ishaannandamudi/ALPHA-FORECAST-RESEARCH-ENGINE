# Descriptive interaction stability

InteractionStability consumes2 or more distinct immutable models with the same exact
rich target/horizon, interaction set, original columns, family, preprocessing and tree
parameters. Fold/time-window/seed identities remain distinct and inspectable. Available
time must follow every model. There is no interaction deletion or new model publication
inside diagnostics.

Linear coefficients are converted to raw slopes beta/scale before comparison.
Sign consistency is the largest fraction of models sharing negative/zero/positive
sign, separately per column. Magnitude drift is max(abs(raw slope))-min(abs(raw slope)).
It is unordered across compatible windows, not a directional drift alarm.

Tree split recurrence is the fraction of models splitting on each exact column at
least once. It does not imply identical topology or threshold stability. Coefficients,
contributions and recurrence describe arithmetic relationships, not causal importance.
Correlation/condition-based automatic orthogonalization is unsupported (AFRE-16).
No automatic pruning, feature selection, invariance framework (AFRE-17) or broad model
selection (AFRE-20) occurs. Dedicated prediction-correlation diagnostics are deferred.
