# Champion/challenger research

AFRE-23 adds engine 0.24.0, champion/challenger schema 1.0 and additive shared store 1.23 / SQLite user_version=24. Earlier schemas remain 1.0; Python 3.11+ and zero runtime dependencies are retained.

The champion is explicit. Challengers are explicit. A `ParticipantReference` pins a frozen producer/output, native family and source schema, target, horizon, output semantics, units, dataset/fold, availability and optional completed AFRE-20 selection / AFRE-21 fusion provenance. A program contains exactly one CHAMPION and one or more CHALLENGER roles. Duplicate logical producer identities are rejected, including aliases with different participant names. Explicit distinct frozen versions can coexist.

The engine wraps existing causal outputs; it does not discover candidates, fit models, recalibrate forecasts, rerun selection, change weights or choose a global winner. Each challenger is assessed independently against the champion on one shared evidence set. Shadow != production. Promotion eligibility != deployment. Rollback eligibility != rollback action. Every assessment and run carries `MANUAL_ONLY`.

See [programs](challenge-programs.md), [shadow evaluation](shadow-evaluation.md), [matching](challenger-matching.md), [criteria](promotion-criteria.md), [context](challenge-health-cost-context.md) and [audit](challenge-audit.md). Predictive metrics do not establish trading profitability. Portfolio construction, risk optimization and execution remain downstream projects.

**Stop after AFRE-25. Final scope: AFRE-25 — Final Integration, Hardening & Research Audit.** AFRE-24 owns final immutable forecast snapshots, provider-neutral API, artifact/model registry, exact versions/schemas, point/probability/calibration/horizon/ranking/context outputs, reproducible publication/retrieval and health/champion metadata. It excludes portfolio optimization and execution. AFRE-25 is final integration/hardening.

AFRE-24 publishes this completed native research evidence through the [immutable service boundary](afre-service-api.md). Exact requested health/challenge metadata is descriptive, retains NONE_DESCRIPTIVE_ONLY / MANUAL_ONLY and never changes forecast values. The registry records metadata without deployment; the read-only service never trains, selects, promotes or executes. Frozen catalogs and exact IDs have no hidden latest. AFRE-25 completes Final Integration, Hardening & Research Audit.
