# Cross-sectional alpha and ranking

AFRE-9 is a relative-ranking research layer, not portfolio construction. It emits
scores, ranks, coverage and provenance. It never emits position sizes, allocations,
orders, leverage or execution decisions. Predictive metrics do not establish trading
profitability. Engine **0.10.0**, cross-sectional schema **1.0**, shared store **1.9**,
SQLite `user_version=10`; earlier public schemas remain 1.0.

`CrossSectionIdentity` pins a representative full ForecastOrigin, exact AFRE-2 target
and typed horizon, AFRE-3 snapshot, eligibility policy and security order. Across
securities, timestamp, availability cutoff, calendar/session, build context and
universe projection must agree exactly. The instrument is the comparison dimension;
it is the only ForecastOrigin field allowed to differ. `CrossSectionSpec` adds exact
model/provider statistic, direction, ties, missingness, normalization, group policy,
ranking layer, historical-delivery approval and implementation version.

One frozen read snapshot builds the exact INCLUDED and ELIGIBLE security grid. All
eligible securities remain in `CrossSectionRanking.entries`, canonically sorted by
stable security fingerprint. Extra/ineligible securities and duplicates reject.
Missing, unsupported, invalid and future sources remain explicit. EXCLUDE_MISSING
and RETAIN_UNRANKED both preserve the audit grid; FAIL_ON_MISSING rejects the build.
Neither policy imputes values. Ranked count/eligible count is coverage. Reasons and
exact group references expose exclusion composition; missingness can bias results.

Each observation pins its own full origin, source and optional PIT membership,
plus the snapshot's exact listing. Issuer enrichment is reserved until exact issuer
evidence is supplied; it is not guessed. RawScore preserves the original sign and
value. Global peer state and group-neutral peer state have separate immutable IDs.
The supplied ranking layer chooses RAW, NORMALIZED or GROUP_NEUTRAL explicitly.

Rank **1 means best**. HIGHER_BETTER and LOWER_BETTER are supplied choices. Exact
numeric ties support AVERAGE_RANK, MIN_RANK, MAX_RANK and DENSE_RANK. No tolerance
merges nearby scores. Percentile is `1-(rank-1)/(N-1)` for N>1; a singleton pure-rank
query returns 0.5. Dense ranks use the same declared N denominator and need not span
the full percentile range. Transformations require an explicit minimum N>=2.

ScoreSource supports POINT_PREDICTION, POINT_EXPECTATION, MEDIAN, QUANTILE,
THRESHOLD_PROBABILITY and EXTERNAL_SIGNAL. Exact model/state/provider versions and
quantile/event definitions are identity-bearing. Raw and calibrated distributions
remain distinct. An unsupported expectation or unrequested quantile/event remains
unranked; there is no guessed distribution. No uncertainty penalty is implicit.

Included predictors and group memberships must be usable by the origin cutoff.
Physical ranking computation is at or after the origin and no later than its cutoff;
the currently supported causal build therefore requires cutoff=origin and computation
at that instant. Later retrospective composition is not backdated into a historical
ranking. Qualified historical delivery concerns input evidence, not fabricated rank
computation. Ranking application reads no current/future target truth.

AFRE-8 horizons are ranked independently. Exact rich target, benchmark, adjustment,
calendar and horizon identities prevent mixing simple/log/residual outcomes or
different horizons. There is no cross-horizon fusion or aggregate rank surface.

`CrossSectionRepository` adds three immutable tables, verified lookup indexes,
canonical safe JSON and additive transactional 9→10 migration. Prior payloads,
DDL and metadata remain unchanged. Exact repeat is idempotent; conflicting stored
bytes reject. Startup validates the full layout; reads check hash/schema/indexes;
deep audit replays membership, scores, transformations, rank, truth and diagnostics.
One bounded lineage spans earlier fits, folds, features, targets and universe evidence.
Backdated corrections require explicit new references and preserve old bytes.

Default bounds: 10,000 securities, 1,000 groups per cross-section, 100,000 stored
external signals/group records, 128 features, 100,000 truth rows/rankings, 10,000
series observations, 100,000 lineage nodes, depth64 and 8MiB serialized/audit bytes.
Hard limits include 100,000 securities and 16MiB canonical payloads. Overflow fails.

See [normalization](cross-sectional-normalization.md), [groups](group-neutral-ranking.md),
[IC](information-coefficient.md), [stability](rank-stability.md),
[external integration](external-signal-integration.md), [profile](cross-sectional-benchmark.md)
and [completion evidence](AFRE_9_COMPLETION_REPORT.md).
