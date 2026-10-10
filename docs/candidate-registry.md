# Immutable candidate registry

CandidateFamilyPlan records the frozen candidate roster for a SelectionRequest.
CandidateFitResult records actual native model/preprocessing/forecast witnesses or
an explicit failure. CandidateValidationResult records criterion values, exact
sample/truth/forecast pairs, exclusions, clocks, status and native trial identity.
SelectionResult records the full pool, ordering, winner/model, usage, exhaustive
status and AFRE-19 family/event references. CandidateRegistrySnapshot records every
candidate's fit, model, validation and trial references at the completion cutoff.

VALID, FIT_FAILED, INCOMPATIBLE, INSUFFICIENT_DATA and NUMERICAL_FAILURE stay visible.
NO_VALID_CANDIDATE has no selected model. An explicitly permitted sole valid model
is NONCOMPETITIVE. A minimum-support exclusion never deletes an opportunity.
Registry replay verifies exact membership and native evidence, not just hashes.

Each candidate receives an AFRE-19 TrialSpecification and ResearchTrial. Failures
use the space's predeclared native PointForecast protocol anchor to define the
opportunity, while their failed trial has no invented observations. The attempted
native phase and candidate remain explicit in choices/spec identity. Successful
but criterion-incompatible point fits retain their native audit observations.
For probabilistic criteria, the native trial channel records squared-error audit
evidence; the exact probability criterion remains separately recorded by AFRE-20.
Unsupported inferential assumptions stay false; selection fabricates no significance.

Native AFRE-19 SelectionEvent uses median effects and native trial fingerprint ties.
AFRE-20 mean MSE/MAE and candidate fingerprint ordering can differ. An event is emitted
only if exact criterion values, direction and complete ordering match. Otherwise
SelectionResult still records the full decision and trial pool with explicit
INCOMPATIBLE_NATIVE_MEDIAN_PROTOCOL. The demo verifies both cases.

Store 1.20 adds sel_artifacts, sel_records and sel_links, five indexes and immutable
SQL triggers. Transactional 20→21 migration preserves prior rows, DDL and metadata,
adding selection version keys only. Failed migration rolls back; future versions,
layout drift, payload/hash/index/link corruption and invalid semantic replay fail closed.
