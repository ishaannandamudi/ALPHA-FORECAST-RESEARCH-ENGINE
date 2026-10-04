# Threshold and tail probabilities

ThresholdRequest pins finite numeric c and one closed comparison: GT (Y>c), GE
(Y>=c), LT (Y<c), LE (Y<=c). ThresholdDefinition sorts by value/comparison and rejects
duplicates; default budget is 64 requests, hard ceiling 256. Every output is finite
and in [0,1]. No outcome enters construction of these probabilities.

For Gaussian mu/sigma, LE and LT equal Phi((c-mu)/sigma), while GT and GE equal the
direct erfc upper tail. Continuous boundary mass is zero. For empirical atoms,
LE counts shifted atoms <=c; LT counts <c; GT counts >c; GE counts >=c. Duplicates
retain equal atom mass. Queries compare the actual finite shifted atom rather than
silently changing equality through inverse subtraction rounding.

For (-2,-1,0,1,2) and c=0: GT=.4, GE=.6, LT=.4, LE=.6. GT+LE=1 and GE+LT=1 within
floating-point tolerance. Strict and inclusive complements differ at empirical
atoms. A deterministic single atom has explicit zero/one probabilities. Normal
upper-tail erfc retains representable probabilities even when 1-CDF rounds to zero.
Unrepresentable extreme-tail mass underflows to zero under the declared numerical
version; no negative or >1 probabilities are produced.

The same comparison is used for the later truth event indicator, including exact
equality. Brier scores are per threshold and aggregated only over the exact declared
request set. QUANTILE_SET cannot request events or imply tail probabilities. Binary
event log loss and probability clipping are not implemented. No probabilities are
turned into positions, portfolios, execution decisions or profitability claims.
