# Explicit descriptive health rules

HealthRule requires supplied warning and degraded boundaries. There are no default severity thresholds, hidden sigma rules or opaque health index. Every threshold, minimum N, direction, statistic, declaration and implementation is identity-bearing and versioned.

HIGHER_WORSE is degraded at score >= degraded, warning at score >= warning. LOWER_WORSE reverses both comparisons. ABSOLUTE_CHANGE_WORSE compares the absolute score to nonnegative boundaries. TWO_SIDED_RANGE has an explicit inner healthy closed range and outer non-degraded closed range: inside inner is HEALTHY, outside inner but inside outer WARNING, outside outer DEGRADED. Boundary behavior is independently tested.

Minimum support is the maximum of the request, spec, both windows and the bound rule. Unsupported values are UNAVAILABLE, incompatible evidence INCOMPARABLE, and inadequate observed support INSUFFICIENT_DATA. Without a HealthRule a calculable metric preserves its values but has UNAVAILABLE status with no-default-threshold reason.

WORST_STATUS pins precedence INCOMPARABLE, UNAVAILABLE, INSUFFICIENT_DATA, DEGRADED, WARNING, HEALTHY. Unknown states precede severity so an aggregate cannot hide missing required evidence. The snapshot contains exactly every declared metric and rule. HEALTHY/WARNING/DEGRADED are descriptive labels, not automatic lifecycle instructions or health-confidence probabilities.

Changed rules, reference windows or monitored artifacts create new immutable identities. Recovery preserves old degraded snapshots. No rule claims a causal explanation or profitability. AFRE-23 may later use health context in explicit champion/challenger evaluation; no promotion, retirement or deployment exists here.
