# Research exposure rules

The implemented closed modes are SIGN, THRESHOLD_SIGN, FIXED_UNIT_NOTIONAL and
DECLARED_SCALAR_EXPOSURE. Bounds are explicit, finite, contain zero and remain within
[−100,100]. SIGN returns ±declared amplitude for nonzero forecast; THRESHOLD_SIGN returns
zero when abs(signal) ≤ threshold, including ties. Fixed unit returns +1; declared scalar
returns its explicit value. Unused mode parameters must be zero. Threshold units are
return_fraction for forecasts or the exact native residual unit; no implicit rescaling occurs.
RANK_BUCKET is unsupported.

Each stable security has its own ordered sample path, irrespective of ticker or changing
peer/universe context. Same-security same-time ambiguity rejects. ZERO and DECLARED_INITIAL
pin the starting exposure separately for every newly encountered security. There is no
inferred initial holding, terminal close, liquidation on universe exit or cross-security netting.
Re-entry retains the last observed exposure along this explicitly supplied path.

`trade_delta = exposure − previous exposure`; prior sample IDs retain exact chronology.
Only causal frozen forecast/signal values influence the mapping. Simple return truth enters
later gross evaluation, never the exposure rule. The reference notional/price used to translate
exposure units into a hypothetical quantity does not create a capital account or portfolio.
See [turnover](turnover-diagnostics.md) and [cost units](spread-fee-slippage.md).
