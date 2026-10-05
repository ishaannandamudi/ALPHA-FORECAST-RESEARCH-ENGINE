# Information coefficient and exact evaluation samples

CrossSectionTruth pins one exact TargetVintage or explicit absence for every
eligible security in the ranking. Full security/origin/target/horizon must agree.
Completed verified truth must be known by evaluation cutoff. REQUIRE_COMPLETE
requires truth for all ranked members; AVAILABLE_INTERSECTION explicitly permits
missing truth. Future/unverified truth remains unavailable. Every evaluation exposes
the exact admitted securities, excluded securities/reasons and N; denominator changes
are never hidden. Realized ranks use the spec's direction and tie convention.

Pearson IC is centered, normalized correlation of the chosen score layer against
realized target outcomes on the exact intersection. It uses the existing bounded
AFRE-5 numerical routine. N<2, constant predictions or constant truth return explicit
undefined PointMetric states and None, never a fabricated zero. The N or N-1 scale
factors cancel in correlation; there is no additional fitted denominator.

Rank IC correlates deterministic ranks of both axes on that same intersection.
AVERAGE_RANK gives conventional tied Spearman. MIN_RANK, MAX_RANK and DENSE_RANK
give explicitly declared alternative tied-rank correlations; they are not silently
called the conventional average-rank estimator. Exact ties have no numeric tolerance.
Predicted threshold probability can be compared descriptively with continuous target
outcomes; this IC is not a probability calibration/proper-score result.

Top/bottom diagnostics require N>=2K, so their exact K sets do not overlap. Rank ties
at a boundary split by canonical stable ID. Top mean minus bottom mean is a
**descriptive top-bottom spread, not a realized tradable portfolio return**. No
weights, transaction costs, turnover, borrow or execution assumptions are inferred.
Insufficient N returns no means/spread. Positive IC or spread never proves profit.

Buckets run from worst to best predicted rank, split deterministically by stable ID
at ties, with adjacent equal-count integer partitions differing by at most one member.
They require N>=the supplied bucket count. Exact memberships/counts and realized
means are retained. Monotonicity is the fraction of adjacent means moving weakly in
the declared favorable direction; it is descriptive. No significance or hit-rate
test is added.

ICSeries stores one observation per exact origin/target/model protocol in temporal
order. Duplicate origins and mixed protocols reject. Undefined values remain counted
in total_count and excluded only from defined_count/statistics. Mean, median,
population standard deviation and strictly-positive fraction are reported on defined
observations. No t-test, confidence interval or multiple-testing control is claimed.

Native TEST forecasts require an explicit evaluation identity and the existing
AFRE-4 sealed access/reuse record. Truth must match the exact pinned ResearchSample.
Idempotent access reuses the same record; changed cutoff/evidence rejects; new access
records preserve prior history. External specialist scores cannot prove the provider's
training or holdout discipline merely from a scalar/provenance contract. Downstream
provider audits must supply that assurance. Ranking and relative fitting never read
TEST labels before this separate evaluation step.
