# Forecast targets and label construction

AFRE-2 established the target truth layer in `afre.target_engine`, at engine 0.3.0,
target schema 1.0. Foundation `afre.targets.TargetSpec` and `ForecastTargetRow`
remain byte-compatible. Rich target definitions are separate contracts: there is
no implicit conversion that changes the foundation first-after-origin convention.
The target layer implements no models, splits, universe ingestion, portfolios or execution.

`TargetDefinition` identifies semantic name/version, type, typed horizon, separate
origin/endpoint rules and tolerances, close price field, raw-input stream and units,
calendar, regular/extended-session policy, exact source datasets, adjustment policy,
benchmark/path estimator and builder version. Names begin `target.`. Arbitrary
parameters and unknown runtime implementations fail closed. A semantic definition
name/version cannot be re-registered with different logic; use a new version/name.

All returns are dimensionless, not percentage points. Let P0 be the explicitly
selected positive origin close and P1 the policy-adjusted endpoint close.

| Type | Explicit estimator |
| --- | --- |
| Simple return | P1/P0 − 1 |
| Log return | log(P1) − log(P0) |
| Residual return | Simple return minus an exact aligned supplied benchmark return |
| Absolute return | abs(P1/P0 − 1) |
| Downside return | min(P1/P0 − 1, 0); signed nonpositive |
| Realized volatility | sqrt(sum of squared consecutive sampled close log returns); no mean subtraction or implicit annualization |
| Maximum adverse excursion | min(0, sampled adjusted close/P0 − 1); signed nonpositive |
| Maximum favorable excursion | max(0, sampled adjusted close/P0 − 1); nonnegative |

Excursions use sampled **closes**, not intrabar highs/lows. Volatility annualization
requires an explicit positive variance multiplier; multiply the squared-return sum
before the square root. No factor fitting, inferred benchmark constituents or beta
estimation occurs. A benchmark is a provider-neutral supplied return with its own
stable instrument, dataset, implementation, nominal window, actual price endpoints
and clocks; its availability constrains the residual label.

`TargetBar` preserves stable instrument, raw close or explicit absent/invalid state,
completed period, timestamp convention, session, neutral source/build, quality,
six clocks and optional predecessor. Source builds pin exact bar-vintage IDs,
calendar, cutoff, action stream and benchmark IDs. Later corrections create new
bar/source/label/dataset identities. Equal-precedence conflicting bars fail closed;
an explicit compatible predecessor chain can establish precedence.

`TargetVintage` pins definition, full forecast origin/universe, source build,
nominal window, actual prices/path/actions/benchmark, completion, availability,
value or explicit absence, typed quality/counts and a deterministic reason.
Missing endpoint, halt, delisting or zero/nonpositive price preserves the sample
as MISSING/INVALID. A not-yet-completed window is NOT_AVAILABLE_YET; a security
excluded by the supplied historical universe is NOT_APPLICABLE. No terminal loss,
stale substitution or missing-print imputation is invented. Quality flags independently
record tolerated endpoints, partial paths, revision, reconstruction and unverified
sources. Partial/unverified computed outcomes remain research evidence and cannot
pass the training eligibility helper.

`TargetSetManifest` pins exact definitions. `TargetDatasetManifest` pins every
origin × definition grid cell, supplied universe, source build, rows, source cutoff,
actual construction time, builder and engine versions. It is target materialization,
not AFRE-4 feature/label joining or splitting. Overlapping intervals remain explicit.

Use `TargetRepository` and `TargetEngine.freeze_source`, `build_dataset`, `rows`,
`targets_known_by`, `audit_target` and `audit`. Training queries can filter exact
origins, stable instruments and a frozen dataset. They return all admissible pinned
vintages; the caller must choose the intended dataset rather than assume an implicit
global latest truth. Run `python -m examples.target_demo` with `PYTHONPATH=src:.`.

See [windows](target-window-semantics.md), [availability](target-availability.md),
[actions](target-corporate-actions.md), [lineage](target-lineage.md) and the
[offline profile](target-benchmark.md).

AFRE-3 adds universe ingestion separately in afre.universe, with engine 0.4.0 and
additive UniverseRepository store 1.3/user_version=4. Target schema and all existing
label semantics remain 1.0. A complete causal snapshot projects to the foundation
UniverseManifest consumed by TargetEngine. Feature and target rows match full stable
security/origin/universe identities; ticker reuse cannot alter that key. Changing
membership or eligibility changes snapshot, manifest and target dataset identity.
No AFRE-4 joins or splits are generated. See [PIT universes](point-in-time-universes.md).
