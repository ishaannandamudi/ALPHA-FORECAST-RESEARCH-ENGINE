# Deterministic resource budgets

ResourceBudget bounds the complete grid's candidates, fit operations, reserved TRAIN
rows, reserved VALIDATION rows, native maximum iterations and serialized payload.
SelectionBounds additionally bounds dimensions, rows per artifact, stored artifacts,
comparisons, SQLite snapshot pages, publication rows and lineage nodes/depth/bytes.
Limits are checked before fitting wherever inputs determine the work, with final
payload and publication limits checked before atomic publication. No partial result
is silently published when a limit fails.

Reservations count each candidate's admitted TRAIN and requested VALIDATION rows.
Native fit operations include baseline preprocessing, nonlinear adaptive transforms
and sequence transform fitting. Numerical iteration reservations sum native declared
max_iterations (one for closed-form families); this is a conservative declared
iteration ceiling, not a FLOP count or elapsed-time guarantee. Other native APIs
retain their own matrix/dimension/solver bounds.

ResourceUsage records reservations, attempted fit operations, fitted candidates,
actual VALIDATION pairs and space/fit/validation payload bytes. Semantic replay
recomputes these values. Payload accounting describes these artifacts, while separate
repository snapshot/publication/lineage bounds cover broader persisted context.
Failed candidates consume their reserved opportunities and recorded attempted work.

Absolute ceilings: 128 candidates, 16 dimensions, 2000 rows per artifact, 128 comparisons,
100000 selection artifacts, 8 MiB payload/lineage, 128 MiB SQLite snapshot, 100000
publication rows, 100000 lineage nodes and depth64. Callers can lower limits.

There is no wall-clock stopping rule, hidden early stopping, adaptive expansion or
BOUNDED_PARTIAL mode. A full grid that exceeds its budget is rejected before fitting.
The [measured profile](selection-profile.json) reports enumeration, native fit
orchestration, VALIDATION scoring, decision, AFRE-19 registration/completion, registry,
audit, atomic persistence, restart and SQLite page storage separately. It is one
small synthetic offline grid, with no production SLA or scale extrapolation.
