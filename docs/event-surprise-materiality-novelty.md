# Materiality, novelty and surprise

EventValue pins numeric value, unit, optional scale bounds, method/version/provider,
information cutoff, source and all AFRE-1 availability evidence. Values are supplied
data or fixed-rule output. No thresholds or novelty corpus state are learned here.
Semantic compatibility includes provider/method/version/unit/scale bounds; changing
scales produces a new conditioning policy. Every used value must be known at origin.

EventSurprise pins actual and expected EventValues with their exact source vintages,
positive normalization and `actual-minus-expectation-v1`. Both units agree; value is
(actual−expected)/normalization. Its semantic key binds both component definitions
and normalization. Computation/availability follows BOTH input availabilities. A
known actual with an unavailable expectation cannot supply surprise. Revised
consensus requires a new exact artifact; no retrospective consensus reconstruction.

EventValueRule declares exact compatibility, fixed inclusive minimum/maximum and
whether the value enters the linear model. No arbitrary interactions. Only configured
admissible attributes enter observations and evaluation buckets; unconfigured
attributes are explicitly labelled unconfigured. Thus a late attribute that was
not used cannot silently enter an explanatory historical breakdown.
