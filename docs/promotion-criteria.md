# Advisory promotion criteria

Each `PromotionCriterion` requires an exact metric request, explicit HIGHER/LOWER direction, nonnegative improvement threshold, minimum common support and declaration clock. Optional required native research context, allowed champion/challenger health statuses and cost evidence are explicit. There is no default threshold, inferred severity, default health prerequisite or automatic promotion.

Comparisons retain raw `challenger - champion` deltas and the metric's separate better/worse orientation. Criteria use their supplied direction, with an inclusive threshold. Health requirements are evaluated only against exact declared participant snapshots, matching target/horizon, current window and cutoff. Missing required evidence produces INCOMPARABLE; small common support produces INSUFFICIENT_DATA. A degraded champion alone cannot satisfy a promotion rule.

`ALL_REQUIRED` is the default. `ANY_REQUIRED` is available as a distinct frozen policy. Each criterion result and reason is retained; unsupported comparisons are explicit. Outcomes are PROMOTION_ELIGIBLE, PROMOTION_NOT_ELIGIBLE, INSUFFICIENT_DATA or INCOMPARABLE. Multiple challengers are assessed independently; no healthiest, newest or best aggregate candidate becomes a winner.

Every `PromotionAssessment` carries `MANUAL_ONLY`. Eligibility is research advice, not deployment, routing, registry mutation or a profitability claim. No automatic production replacement, retraining, recalibration or fusion changes occur.
