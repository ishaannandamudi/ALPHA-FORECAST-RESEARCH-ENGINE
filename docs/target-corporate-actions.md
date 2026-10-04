# Corporate-action target semantics

The initial neutral target adapter accepts **raw inputs only**, with a declared
price unit and bar stream. Target definitions explicitly fingerprint RAW,
SPLIT_ADJUSTED, TOTAL_RETURN or EXPLICIT_ADJUSTMENT_STREAM. Inputs are never silently
pre-adjusted or mixed. The foundation AdjustmentPolicy contract is unchanged.

RAW ignores actions and calculates the raw close outcome. SPLIT_ADJUSTED uses each
qualified split ratio as **new shares per old share**. For a 2-for-1 split between
P0=100 and raw P1=50, RAW return is −0.5 and SPLIT_ADJUSTED return is 0.0. Later
prices are expressed in origin-share units by multiplying applicable split ratios.
Each sampled path price is adjusted only for actions effective after its selected
origin close and at/before that price. Reverse splits use the same positive-ratio
contract. Splits at the selected origin are excluded; splits at the endpoint included.

An explicit stream uses positive supplied price multipliers with the same effective
interval. It rejects split/cash records masquerading as price factors. Split-only
adjustment permits cash-distribution records as evidence but deliberately ignores
cash: the result is not total return. Unknown action kinds are closed enum failures.
TOTAL_RETURN and dividend reinvestment are **contract-only** and always fail with a
clear unsupported-policy error; AFRE-2 never pretends to calculate total return.

`TargetCorporateAction` pins stable instrument, event ID, effective time, kind,
positive ratio/amount, source dataset, clocks, provenance and optional compatible
predecessor. `TargetActionStream` pins exact action IDs, dataset/build version,
coverage start, complete-through time, availability and evidence. Coverage cannot
claim completion past stream availability. Non-raw construction requires a stream
covering the entire selected price interval, admitted by the source cutoff; incomplete
coverage returns NOT_AVAILABLE_YET, an absent stream returns MISSING. This distinction
prevents interpreting an empty unqualified action list as proof that no split happened.

Selection uses stable security and event identity. Later admitted revisions are new
artifacts; ambiguous equal-precedence action corrections fail closed. Final label
availability respects the entire required stream and selected actions, including a
late announcement/correction. Frozen datasets retain old stream/action IDs and bytes.
No live corporate-action service, dividend reinvestment, tax/FX treatment, portfolio
adjustment or execution is implemented.
