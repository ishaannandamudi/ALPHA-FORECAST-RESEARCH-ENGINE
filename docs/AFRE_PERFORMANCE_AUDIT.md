# Final bounded release profile

Measured engine1.0.0 / API1.0 / store1.24 / SQLite25 using actual native workflows. The successful release demo asserts85 checks, including actual native forecasts/laws/contexts, independent1h/1d horizons, public consumer behavior, corrections, restart, ordering and descriptive/manual boundaries. [Full measurements](release-profile.json) and [asserted checks](release-demo-evidence.json) are recorded separately from semantic identities.

The instrumented run took536.2180835420731 seconds on this local Python3.11.16 / SQLite3.53.4 environment. This is one bounded synthetic offline profile, not a production SLA or scalability claim. Cumulative operation times include nested validation/persistence and can overlap. Exclusive Python self-time buckets follow the exact path/name rules in benchmarks/release_profile.py; builtin/SQLite C frames and other Python frames are outside those buckets. The algorithm bucket includes other AFRE assembly/serialization/hashing work, rather than pretending all residual time is pure fitting.

| Native operation | Calls | Cumulative seconds |
| --- | --- | --- |
| baseline fitting | 12 | 3.457152288 |
| calibration | 8 | 2.230162583 |
| challenge evaluation | 2 | 0.724209791 |
| dataset admission | 8 | 15.817354500 |
| event regime conditioning | 56 | 10.133444249 |
| feature reconstruction | 56 | 0.952033500 |
| fusion | 7 | 0.889473626 |
| health monitoring | 2 | 0.427195917 |
| multi horizon assembly | 3 | 10.593406417 |
| probabilistic prediction | 13 | 2.897485417 |
| registry lookup | 1 | 0.026173458 |
| selection | 1 | 8.195306625 |
| service replay | 34 | 16.813339332 |
| signal ranking | 3 | 1.049660250 |
| snapshot publication | 48 | 75.146065791 |

Explicit stage measurements separately record fixture-construction wall time, native solver/design-matrix work, dataset assembly/PIT admission/persistence, selection admission/fitting/trial completion/scoring/decision/atomic persistence, audit, public publication, registry lookup, backup and restart. Fixture construction itself executes real native methods, which remain visible in the call profile. No benchmark timing is a content fingerprint input.
