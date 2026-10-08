# Cost scenarios and availability

`CostScenario` pins a simple-return target/horizon, fold, exact source/sample IDs, bounded
exposure rule and initial policy, complete sample × component binding grid, one explicit
price/notional/liquidity assumption per sample, currency, signal units, participation limit,
maximum input age, missing/fallback policy, quality opt-in, qualified-delivery attestors,
optional uncertainty metadata and closed implementation/turnover/contribution conventions.
Component/provider versions, applicability and declarations are identity-bearing. Arbitrary
code/model names or provider-selected filesystem paths cannot be loaded.

`CostInputReference` distinguishes upstream publication, upstream source availability,
actual AFRE observed/received, ingestion, computation and final availability. Provider clocks
are not automatically AFRE availability. Live usable time cannot precede actual receipt.
A historical archive downloaded months later remains reconstruction, not causal evidence,
unless exact source/security qualified delivery evidence establishes earlier historical
knowability with an explicitly approved attestor. Actual ingestion/computation clocks remain
later. Output artifacts record actual construction even when qualified input final availability
is earlier; they cannot pretend to have been produced historically.

HISTORICAL_CAUSAL inputs require final availability ≤ the exact origin availability cutoff,
as-of time ≤ origin time, valid declared age and actual AFRE computation ≤ actual cost
construction. Publication at 10:00 and receipt at 10:02 cannot support origin 10:01. EX_POST_RESEARCH
may use later evidence, is labeled everywhere, and cannot be returned as causal origin-time
metadata. Both modes require evidence actually available by construction/evaluation. Liquidity
and cost refs must match exact security/currency; horizon-bearing volume and impact
coefficients must match the target horizon. No FX or latest-vintage substitution occurs.

Quality is VALID/MISSING/STALE/DEGRADED/UNSUPPORTED/INVALID. DEGRADED requires explicit
opt-in. FAIL rejects unusable inputs; EXCLUDE_SAMPLE retains the full exposure path and
explicit missing amounts/reasons; DECLARED_FALLBACK uses a pinned nonnegative rate only
when rate evidence is missing and liquidity is usable. Missing liquidity never silently
receives a quantity, price, notional or zero-cost fallback. Actual zero is accepted only as
an explicit declared value, or a known zero trade delta.

All rule/component settings and sensitivity grids precede the fold TRAIN cutoff. This is a
caller-attested chronology contract, not proof that a researcher was blind to later outcomes.
TEST seals a frozen assessment and cannot tune thresholds, spreads, impact, participation,
fallbacks, grids or supplied models. Corrections append new inputs/models/scenarios/results.
See [research semantics](transaction-cost-aware-research.md).
