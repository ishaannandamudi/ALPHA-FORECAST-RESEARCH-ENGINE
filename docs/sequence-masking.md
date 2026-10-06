# Sequence missingness and padding

Each snapshot contains values, observation IDs and a boolean mask at every timestamp/feature cell. Real zero is `(0.0, True)`; a missing or padded cell is `(None, False)`. A sourced missing token retains its observation ID and quality, while an alignment gap or padding has no source ID. Missing, stale, invalid and withheld source states are distinguished; no silent forward fill, interpolation or missing-value zero replacement occurs.

`LEFT_PAD_MASKED` and `RIGHT_PAD_MASKED` pad to the maximum count with None timestamps/encodings and all-false masks. `FAIL_IF_SHORT` requires maximum count effective timestamp rows for fixed windows, and the minimum effective row count for elapsed windows. One missing feature does not erase other features in a row. Fitting/prediction require at least one unmasked token for every model feature.

`COMPLETE` means sufficient history with no missing/padded cells. `PARTIAL` means the minimum is met but masks/padding remain. `INSUFFICIENT` means fewer effective timestamp rows than minimum; `UNAVAILABLE` means no admissible timestamps. A row counts as effective if at least one feature is unmasked. Diagnostics preserve effective counts, oldest/newest ages, actual gaps, masked fraction and explicit exclusions.

Decay aggregation skips masked cells. State-space recurrence skips the update of a masked feature and leaves that state unchanged; padding never advances recurrence. These supplied semantics are part of model identity. [Families](sequence-model-families.md).
