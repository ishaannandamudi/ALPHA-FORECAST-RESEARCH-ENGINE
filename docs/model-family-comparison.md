# Native model families and matched comparisons

AFRE-20 routes immutable recipes into existing fitting APIs. It does not reinterpret
coefficients, dynamics, solver convergence or provider evidence.

| Family | Selection adapter |
| --- | --- |
| AFRE-5 statistical baselines | native TRAIN preprocessing/fit, frozen point forecasts |
| AFRE-6 probabilistic | native distribution fit and compatible CRPS/Gaussian NLL |
| AFRE-10 event conditioning | exact TRAIN observations and VALIDATION observation/base bindings |
| AFRE-11 regime conditioning | exact native state fit and VALIDATION state/base bindings |
| AFRE-13 nonlinear | native TRAIN transforms/matrix/fit, exact VALIDATION scalar inputs |
| AFRE-14 sequence | native TRAIN transform/dataset/fit, exact VALIDATION snapshots |

All six adapters have real native fit/forecast/restart fixtures. AFRE-12 mixture
orchestration and automatic calibration candidate selection remain unsupported.
Seed, preprocessing, model and feature variants are explicit native specs, with no
hidden parameter replacement. Uncertainty/stability IDs may serve as guarded metadata
references; they do not automatically become ranking penalties or evidence for refit.

The AFRE-16 adapter validates residual projection/source/origin/value/availability and
publishes an explicit native scalar feature. A later fold consumes the actual scalar
in its nonlinear feature input. Residuals must be available at each origin; samples
declared TEST anywhere in the same dataset cannot be reclassified into this search.
Orthogonal does not mean independent, causal alpha or profitability.

CandidateComparison uses the exact common (sample ID, truth ID) intersection, common
target/horizon/dataset/fold/criterion/cutoff and declared minimum support. Metrics are
recomputed on this intersection; delta is B minus A. It is descriptive, with no
fabricated significance or preference inversion. Fewer matched rows gives unavailable
metrics. Cross-horizon comparisons and outcome-dependent cohort changes are rejected.

AFRE-18 hypothetical cost evaluation remains separate research evidence. It is not
portfolio construction and is not an AFRE-20 criterion. Model selection remains
separate from AFRE-21 ensemble construction and later portfolio/risk/execution projects.
