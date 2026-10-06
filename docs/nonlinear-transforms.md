# Finite nonlinear transforms

| Transform | Exact policy |
| --- | --- |
| IDENTITY | x |
| PRODUCT | x*y, two explicit operands |
| RATIO | x/y with mandatory FAIL_ON_ZERO, MISSING_ON_ZERO or EPSILON_FLOOR |
| DIFFERENCE / ABS_DIFFERENCE | x-y / abs(x-y), equal units |
| SQUARE / CUBE | x² / x³; maximum explicit degree3 |
| LOG1P_SIGNED | sign(x)*log1p(abs(x)); zero stays zero; dimensionless input |
| CLIPPED_LINEAR | min(upper,max(lower,x)); fixed explicit bounds |
| PIECEWISE_LINEAR | Linear interpolation between exact knots/ordinates; clamp outside |

EPSILON_FLOOR pins positive epsilon and replaces denominator magnitude below epsilon
while retaining sign; canonical signed zero is positive. MISSING_ON_ZERO yields None,
which a model FAIL policy cannot use. Input absence uses the definition's explicit
FAIL, propagate None or finite declared output fallback. Zero is never missing.
NaN, infinity, overflow and undefined arithmetic fail explicitly.

Piecewise knots are fixed by specification or fitted from exact complete admitted
TRAIN scalars with AFRE-4 Type-7 quantiles: position=(N-1)*q and linear interpolation.
Levels/ordinates are supplied, not chosen using labels. Repeated fitted knot values
reject; there is no hidden collapse or resampling. Maximum16 knots. Fitting requires
present inputs; application is target-free. Held-out inputs/labels cannot alter knots.

Derived availability is max(input availability,fitted transform availability,actual
computation). TRAIN application happens at fit time and cannot be claimed as deployment
at older sample origins. No historical feature-computation proof contract is invented.
No splines, signed-product convention, automatic crosses, monotonic constraints or
provider executable transforms are advertised.
