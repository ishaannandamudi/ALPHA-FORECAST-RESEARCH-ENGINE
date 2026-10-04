# Purged walk-forward folds

A target information interval uses the actual AFRE-2 origin/endpoint price times,
including tolerated endpoint policies. If prices are unresolved, the pinned nominal
window remains available when AFRE-2 supplied one. Session and bar horizons retain
those resolved endpoints; an elapsed-day approximation is never introduced.

Default target intervals are (actual origin close, actual endpoint close]. Two
intervals that only touch overlap exactly when both touching ends include the point.
Full information intervals are [earliest declared feature effective/lookback start,
actual target endpoint], including the initial feature information and bounded
feature-input/normalization lineage and referenced market-bar periods. This is deliberately
more conservative and never substitutes one fixed horizon for every target.

PurgePolicy supports NONE, TARGET_INTERVAL_OVERLAP and
FULL_INFORMATION_INTERVAL_OVERLAP. A candidate TRAIN sample is purged when its
chosen interval overlaps a validation or sealed-test sample's interval in the selected
scope. Protected intervals are merged into sorted unions by scope, then queried with
binary search and at most two endpoint-aware comparisons per training interval.
This avoids an all-pairs training × validation loop. Total comparisons have an explicit
bound and overflow fails before publication.

| Scope | Group evidence |
| --- | --- |
| SECURITY (default) | Full stable security identity |
| ISSUER | Exact security-master issuer used by the snapshot, or compatible explicit binding |
| SECTOR | Typed historical ResearchGroupBinding |
| MARKET | Typed historical ResearchGroupBinding |
| GLOBAL | Every security shares the protected boundary |

Bindings require stable security, group, [start,end) validity, known cutoff and neutral
source provenance in the dataset source contract. Conflicting or absent required
bindings fail. Broadcast AFRE-1 features still require their own PIT ScopeBinding;
a purge group does not grant feature scope access. Global/group purging can protect
cross-sectional shared outcomes. Cross-sectional ranking/neutralization and learned
factor transformations remain later phases.

The demo uses short and long horizons, explicit failed cells, advancing fit cutoffs,
interval purging, active embargo and TRAIN statistics. Samples with ready nonoverlapping
labels remain TRAIN; a long target crossing validation is PURGED; a short target whose
publication/computation is still later than fit cutoff cannot become TRAIN.
