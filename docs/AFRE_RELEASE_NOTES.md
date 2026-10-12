# AFRE 1.0.0 release notes

The final research architecture covers all 26 distinct phases, AFRE-0 through AFRE-25. Service API, snapshot/registry and earlier public schemas remain1.0. Store1.24 / SQLite25, Python3.11+ and zero runtime dependencies remain supported. Release status is **RELEASE_CANDIDATE** after all critical gates passed; [the report](AFRE_25_COMPLETION_REPORT.md) and [saved validation evidence](release-validation-evidence.json) record the exact results. Engine1.0.0 means audited research architecture, not production deployment readiness.

The audit fixed a genuine engine-upgrade defect: old public snapshots, audits, version catalogs and replies had validation tied to the running version. A closed historical catalog plus recorded-version semantic replay now preserves0.25.0 records unchanged; new snapshots and envelopes identify1.0.0. Existing public fields, exports and method signatures are unchanged. No earlier model family or persisted schema is redesigned.

New deliverables include native multilayer correction/determinism/migration/security/consumer regressions, an offline public-contract adapter, a bounded release demo/profile, a deterministic source manifest and formal architecture/temporal/research/security/reproducibility/migration/handoff audits. Historical completion reports and benchmark evidence remain historical.

There is no hidden latest, active-model pointer, automatic training/calibration/promotion, portfolio/risk optimizer or execution. Quantile-only density, joint horizon law, guaranteed conformal coverage under nonstationarity, uncertainty component identifiability without assumptions, executable capacity and profitability remain unsupported. Optional improvements belong to post-1.0 considerations, not a new roadmap phase.

Run the documented checks before adoption. No commit, push, external integration or deployment is performed by this task. Review the working tree, release manifest, exact gate logs and unsupported claims before downstream use.

The audit also fixes native research staging on later stores: selection and fusion trial registration retain the concrete repository layout and configured bounds in frozen copies. Their publication remains limited to the existing immutable native tables. Final-store regression tests exercise actual selection and fusion trial registration; earlier phase tests preserve original behavior.
