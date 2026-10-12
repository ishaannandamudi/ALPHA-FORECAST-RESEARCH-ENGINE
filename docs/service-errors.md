# Stable service errors

A failed public read returns `ServiceReply(status, None, safe_message)` with API/service schema 1.0. Raw SQLite exceptions, internal paths and implementation diagnostics never appear in consumer errors.

| Status | Meaning |
| --- | --- |
| NOT_FOUND | Exact identity or selector has no admitted result. |
| INCOMPATIBLE | Producer/target/horizon/origin/context mismatch or ambiguous exact selector. |
| UNAVAILABLE | Explicit capability or pinned context is unsupported/absent. |
| INSUFFICIENT_DATA | Native output has no supported value. |
| INVALID_REQUEST | Invalid selector/cursor/request shape. |
| VERSION_MISMATCH | Requested API version differs. |
| BOUNDS_EXCEEDED | Configured or hard resource limit exceeded. |
| CORRUPT_ARTIFACT | Canonical bytes, hash, layout, index, link or semantic replay is invalid. |

Publication is explicit and strict: invalid native/source/context evidence raises a contract error before atomic append. The consumer read façade never trains, promotes, changes champion or executes. AFRE-25 completes the final integration and hardening audit.
