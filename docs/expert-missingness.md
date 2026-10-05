# Missing expert semantics

Every request supplies all declared expert IDs, each with an exact binding or explicit None.
Available, absent, producer/forecast quality, late receipt, stale as-of, unapproved historical
delivery and unsupported expectation remain distinct reasons. Missing value and contribution
remain None; zero effective weight does not invent a zero-valued forecast.

FAIL rejects unavailable positive original mass. DROP_AND_RENORMALIZE divides available
original weights by their positive total, preserving originals and reasons; no usable positive
mass fails. USE_DECLARED_FALLBACK assigns effective weight1 to the exact declared set member,
all other weights0. An unavailable fallback fails. A missing zero-weight expert remains
recorded and does not trigger a fallback. Negative/signed forecast weights are unsupported.

Availability is checked against the full origin cutoff; as-of age is checked against the
explicit maximum age (default0). There is no implicit latest-provider lookup. Later corrections
produce new immutable forecast/binding/request/mixture identities; earlier bytes remain intact.
