# Irregular sequence time

All ordering and boundaries use exact integer UTC nanoseconds. Encoding converts only known selected timestamps to seconds. `NONE` yields zero for each real timestamp; `DELTA_SECONDS` yields zero at the first real timestamp and actual successive gaps thereafter; `AGE_FROM_ORIGIN` yields `(cutoff-t)/1e9`; `NORMALIZED_POSITION` yields ordinal positions from 0 to 1 (a single token is 0). Padding encodings are None. Position is not elapsed-time scaling.

The models do not learn a time scale. Decay uses actual age in seconds independent of encoding. Diagonal state-space dynamics are explicitly per unmasked observation, not per second; irregular elapsed intervals are retained in encoding/diagnostics and do not imply regular sampling. No calendar/session interpretation or hidden resampling is applied. All encoding choices are pinned in the window fingerprint.

Independent fixtures use irregular gaps and exact open/closed boundary combinations. No future tokens, centered rolling windows or bidirectional future context are admitted. [Causal fitting](causal-sequence-training.md).
