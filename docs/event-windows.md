# Explicit event windows

EventWindowSpec pins exact target/horizon, PRE_EVENT / AT_EVENT / POST_EVENT /
POST_EVENT_DELAYED, anchor, elapsed UTC basis, lookback, minimum delay, maximum age,
inclusive bounds and implementation. Calendar/session/bar event windows are not
advertised. Target horizons retain their original typed identity.

Distance is origin minus the declared occurrence/publication/final-availability
anchor. PRE_EVENT requires distance<0, within the lookback; AT_EVENT requires0.
POST_EVENT requires distance>0 within minimum/maximum delay; POST_EVENT_DELAYED
also requires positive minimum delay. Minimum and maximum edge inclusion are
explicit. Occurrence=None excludes an occurrence-anchored event; another anchor
must be deliberately selected. Maximum age is a window cutoff, not a fitted decay.

These temporal tests never bypass information availability. Pre-event matching
forbids post-event reactions even if a provider submits them with a misleading
as-of. A reaction must also have anchor≤as-of≤origin, as-of≥known occurrence and its own availability≤cutoff.
