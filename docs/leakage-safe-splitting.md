# Leakage-safe temporal splitting

SplitDefinition fixes dataset-independent schedule/policies, version, optional
preprocessing specs and an optional parent fold. ResearchSplit binds it to one
immutable dataset. FoldDefinition pins ordinal, exact ranges and training cutoff;
FoldMembership assigns every dataset sample exactly one partition with a reason.
All ranges for origin membership are [start,end). Each training cutoff lies between
train end and validation start and cannot exceed the dataset processing cutoff.

| Strategy | Repeated-fold behavior |
| --- | --- |
| FIXED_HOLDOUT | One fold; zero step |
| WALK_FORWARD | Fixed train start; advancing train end, validation and cutoff |
| EXPANDING_WINDOW | Explicit expanding training range; same temporal schedule as walk-forward |
| ROLLING_WINDOW | Both training boundaries advance by the declared step |

A common optional final TEST range starts after every validation window. It never
enters TRAIN or VALIDATION in any fold. Separate test queries require an evaluation
identity, purpose and truth cutoff, and persist TestEvaluation including prior
recorded evaluations. Reusing the same identity with changed purpose/cutoff fails.
This is a semantic research seal with explicit reuse evidence, not filesystem or
user access control. Statistical test reuse governance belongs to AFRE-19.

Classification preserves dropped/noncausal samples as INELIGIBLE first. TEST and
VALIDATION depend on historical origin membership; future truth is not needed to
establish membership. Missing, pending and unverified target truth do not change
those origin memberships. Candidate training rows then receive PURGED, EMBARGOED or,
only if the exact AFRE-2 target is known at the cutoff, TRAIN. Remaining candidates
are INELIGIBLE with a label-readiness reason. Purging precedes embargo; both exclude
labels that might otherwise be ready. Explicit failures remain observable.

`training_samples_for_fold` verifies the completed window, actual completion,
verified source quality and final label availability <= cutoff; equality is eligible.
`validation_samples_for_fold` returns membership independently of later truth,
or filters with an explicit evaluation cutoff. `test_samples_for_fold` returns only
known pinned test truth and records the evaluation. Newer label revisions require a
new dataset, rather than silently changing an old fold's labels.

Nested split preparation uses parent_fold_id. Inner TRAIN/VALIDATION/TEST candidates
must all belong to that parent's TRAIN set. This prepares a boundary for later
nested model selection; AFRE-4 does not search hyperparameters or fit predictions.

Defaults are security-local target-interval purge and zero elapsed AFTER embargo.
Purge NONE is explicit and does not claim overlap safety. Any protected sample with
an unresolved interval makes an enabled purge fail, rather than silently certifying
an unknown boundary. Fold queries and audits recompute the complete expected
membership and reject missing, extra or contaminated partition records.

## AFRE-7 calibration reservations

Calibration sample is fit data. [CalibrationPartition](calibration-partitions.md)
uses explicit reserved IDs and origin ranges over existing fold memberships;
VALIDATION is never silently reused. Dedicated, strict TRAIN-tail and rolling-past
policies preserve AFRE-4 partitions. Underlying model TRAIN and TEST cannot fit
calibration. Raw forecasts must have existed at the historical origin and truth
must be available by the calibration cutoff. TEST remains later evaluation only;
independent calibration evaluation also excludes actual calibration fit samples.

## AFRE-9 boundary

AFRE-9 relative models reuse admitted AFRE-5 TRAIN matrices and exact full origin grouping. Optional target centering is TRAIN-only. Later native TEST rank evaluation preserves the existing AFRE-4 seals/reuse and exact pinned truth; it cannot influence fitting or ranking. See [IC](information-coefficient.md).

## AFRE-10 integration

Event observations pin the exact base fold and ResearchSample partition. Fitting admits only exact TRAIN matrix rows with known targets; event/reaction information is checked at each sample origin. Native TEST comparisons require persisted access records. Overlap relations do not create independent samples.
See [event-conditioned forecasting](event-conditioned-forecasting.md).


## AFRE-14 sequence integration

Sequence transforms/readouts require the exact complete admitted TRAIN set and per-sample source cutoffs; TEST/VALIDATION never choose windows or dynamics.
See [temporal sequences](temporal-sequence-models.md) and [causal sequence training](causal-sequence-training.md).
AFRE-15 uncertainty decomposition is complete; AFRE-16 Signal Orthogonalization & Redundancy Analysis is complete; AFRE-17 Invariance & Stability Research remains deferred; predictive metrics do not establish profitability.

## AFRE-16 integration

Signal projections and preprocessing use complete admitted TRAIN signals only; the candidate is the projection response. Forecast-target readouts use only known TRAIN target vintages in a separate API. Held-out metrics share exact intersections and TEST seals; they cannot choose reference sets or tune the projection.

See [signal orthogonalization](signal-orthogonalization.md). Supplied candidate/reference sets are fixed;
no automatic pruning or broad signal search occurs. Orthogonal != independent, residuals are not
guaranteed alpha, and predictive metrics do not establish trading profitability. The frozen roadmap
remains26 distinct phases, AFRE-0 through AFRE-25; AFRE-17 Invariance & Stability Research is deferred.
