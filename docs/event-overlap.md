# Overlapping events

Every match set pins all candidate event/reaction/mapping refs, eligibility distances,
features, selected events and exclusion reasons. No implicit latest event lookup.
FAIL_ON_MULTIPLE fails closed when more than one event matches. NEAREST_EVENT selects
minimum absolute distance with canonical fingerprint tie-break, preserving discarded
eligible relations and their reasons. ALL_EVENTS_SEPARATE emits one observation per
sample/event relation. No aggregate-event offset family is implemented.

ALL_EVENTS_SEPARATE uses explicitly declared unit weight per TRAIN relation. Repeated
labels are correlated; minimum samples and class counts use DISTINCT ResearchSample
IDs, while regressions/class means weight each relation. This policy may emphasize
samples with several events and never treats duplicate relations as independent
research evidence. Evaluation compares at most one forecast per ResearchSample;
overlap relations must be evaluated separately. Ranking also requires one forecast
per security. Single/multi/no-overlap counts are descriptive only.
