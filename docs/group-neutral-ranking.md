# Point-in-time group-neutral ranking

GroupMembership is provider-neutral. SECTOR, INDUSTRY, SUBINDUSTRY and CUSTOM are
typed categories; provider, taxonomy and version are exact identity fields. No GICS
assumption is built in. Membership uses a half-open valid interval and the existing
six-clock AvailabilityEvidence. It must apply at the forecast origin and be known
by the cutoff. Qualified reconstruction requires an explicitly approved attestor.
Current classifications cannot replace historical evidence.

GROUP_DEMEAN subtracts the mean raw score among the admitted same-origin members of
each exact group. It creates a separate PeerState with raw input IDs, exact counts,
group means, unavailable members and output values. Global normalization is another
artifact. These transformations are never silently combined. GROUP_ZSCORE is not
implemented.

Minimum group count>=2 and small-group policy are supplied. FAIL rejects insufficient
or missing groups. MARK_UNAVAILABLE withholds the group's scores. LEAVE_RAW preserves
raw scores for an identified small group, so those values do not claim neutrality;
a missing classification still stays unavailable. A future, expired, wrong-security
or mismatched-taxonomy explicit reference rejects rather than being substituted.
Exclusion composition can change group means; neither ranking nor evaluation claims
that missingness is unbiased.

Lookup uses bounded indexed histories. A newer available classification can be
selected for a new build; conflicting equal-availability vintages fail and require
the caller to pin an exact correction. A published ranking always retains its own
exact reference. Second-writer and later-reclassification tests prove historical
bytes remain unchanged.

Evaluation reports pooled group-demeaned IC: on the exact score/truth intersection,
subtract that evaluation subset's group means from both axes, retain only groups
meeting the supplied minimum, then correlate the pooled residual vectors. It reports
the exact group-security set and N separately from global IC. It never inserts
unavailable truth or recomputes application scores from evaluation truth. A two-member
group can give perfect magnitude correlation without broad predictive evidence.
There is no sector allocation or portfolio neutralization.
