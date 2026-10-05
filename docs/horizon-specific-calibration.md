# Horizon-specific calibration

Every calibrated horizon pins its exact AFRE-7 CalibrationSpec and CalibrationState,
raw probability spec/model and rich TargetDefinition. Application validates target,
raw model, full origin and point/probability chain. A short-horizon state cannot
calibrate a long-horizon forecast merely because both expose P(return>0).
The event key includes target/horizon as well as threshold and strict comparison.

AFRE-8 performs no cross-horizon calibrator pooling. The supported ownership map
marks calibration HORIZON_SPECIFIC. Probability mappings, quantile offsets and
conformal intervals retain their own causal non-TEST fit evidence and clocks.
Long labels cannot enter a short-horizon/shared fit before they are known.

Raw and calibrated surfaces are selected explicitly. Adjusted marginals do not
imply a coherent calibrated PDF/CDF, expectation or variance. A calibrated median
comes from its own q0.5; a calibrated expectation is available only when AFRE-7
IDENTITY preserves the entire raw distribution. Missing calibration stays MISSING
rather than falling back silently to raw values. Raw values remain immutable.

The initial shared linear backbone offers point forecasts only; fitting separate
uncertainty and calibration for those shared outputs requires a later explicit
extension. Existing independent uncertainty is never attached to another model.
