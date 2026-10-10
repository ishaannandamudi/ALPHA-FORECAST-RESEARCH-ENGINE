# Selection read isolation

SelectionRepository applies read-role guards before get, resolve and cached get_any
responses. PLANNING uses the inherited feature-only boundary and metadata-only native
fold geometry. No numeric TargetVintage, training matrix or selection/evaluation
result may enter planning. Metadata checks validate exact dataset/sample/feature/
target identity and native purge/embargo geometry without reconstructing numeric labels.

FIT may read exact TRAIN truth and native TRAIN model witnesses. It rejects VALIDATION
and TEST TargetVintage, stored held-out evaluations, selection results and completed
trial response records. VALIDATION may read declared TRAIN/VALIDATION evidence for
semantic native replay and scoring, never TEST. Exact origin/target identity is
checked before target decoding, including cached targets and later revisions.

Native held-out evaluation payloads are rejected during all selection roles. TEST
forecasts, seals, global TEST registry evidence and TEST-bearing trials are blocked.
ResearchSample metadata can include full fold geometry; its numeric truth is a
separate guarded reference. TEST samples declared by another fold of the same dataset
cannot be reclassified as TRAIN/VALIDATION in a later selection.

The isolated SQLite backup physically copies pages, including held-out storage; it
does not logically decode TEST response payloads. Closed native recipe execution and
mandatory repository APIs implement the read boundary. This is not an arbitrary
private-SQL sandbox, nor authentication of an upstream scalar secretly derived from
future responses. Provider audits and explicit historical-delivery evidence remain
necessary; provider publication does not replace actual AFRE receipt.

Regressions preload cached TEST truth/evaluations before every role/access path,
deliberately corrupt a TEST truth payload as a read detector, reject later-fold TEST
reclassification, preserve preprocessing and perturb TEST source data concurrently.
No selected-model refit or TEST evaluation is exposed by SelectionEngine. Later native
evaluation must carry a TEST seal and AFRE-19 adaptivity/reuse history, rather than
pretending a VALIDATION-selected winner was independently predeclared.
