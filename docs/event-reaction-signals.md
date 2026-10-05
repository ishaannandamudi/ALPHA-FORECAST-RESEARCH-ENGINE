# Neutral post-event reaction signals

AFRE-10 consumes the unchanged AFRE-9 ExternalSignal / ScoreSpec data boundary.
Pin provider/version/schema/name/version/semantics/unit, stable security, as-of,
source/hash, quality and all availability clocks. Supply exact immutable refs;
multiple admissible reaction vintages for a required feature fail as ambiguous.
Matching requires exact semantic key and security, own availability≤origin cutoff,
anchor≤as-of≤origin, as-of≥known occurrence and declared maximum age. PRE_EVENT prohibits reaction features.
Event availability does not imply reaction availability.

Supplied order flow, spreads, liquidity, volume, microprice, toxicity or specialist
predictions are data. AFRE implements none of those algorithms and imports no AME
or EIE code, sibling paths, private classes or databases. The downstream HFT system
implements adapters. Executable provider payloads and execution state are excluded.
Event-conditioned scores can themselves become explicit neutral AFRE-9 inputs,
with source fingerprint/hash tied to the conditioned forecast. This bridge does not
claim historical receipt earlier than the forecast's actual causal availability.
