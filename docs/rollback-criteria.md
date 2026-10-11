# Advisory rollback criteria

`RollbackCriterion` pins an exact earlier frozen champion `ParticipantMetricResult`, request, HIGHER/LOWER deterioration direction, inclusive threshold, minimum support, declaration clock and optional required health states. The baseline must exist and be available by declaration. It is not inferred from the best past result or automatically reset.

The current and baseline metrics must retain the same logical producer, exact target/horizon/unit/request and cost plan. The earlier window must end before the current window begins. Different windows have their own exact support; their identities remain visible. This is explicit temporal deterioration advice, not a claim that the two periods are independent causal experiments.

`RollbackAssessment` retains baseline/current IDs, signed oriented deterioration, reason and outcome: ROLLBACK_ELIGIBLE, ROLLBACK_NOT_ELIGIBLE, INSUFFICIENT_DATA or INCOMPARABLE. Missing/unsupported metrics and incompatible baselines stay explicit. Required health evidence must satisfy the same exact native window and cutoff checks as promotion.

Every assessment carries `MANUAL_ONLY`. Rollback eligibility != rollback action. The engine has no production switch, active-model flag, retirement, routing, retraining or recalibration operation. Earlier runs, forecasts and thresholds stay immutable.
