# Normalization lineage

AFRE-1 records learned normalization state without fitting it or constructing
folds. `NormalizationSpec` names an exact raw feature, method and implementation.
Methods include NONE, STANDARDIZE, ROBUST_STANDARDIZE, MINMAX, RANK and WINSORIZE;
only STANDARDIZE is executable in the initial trusted transformation registry.
Other methods are typed supplied-state metadata, not fitted algorithms.

`NormalizationState` pins exact feature vintage fit sample IDs, fit cutoff,
state availability, source dataset and immutable supplied parameters. Fit samples
must belong to that feature/dataset, be PRESENT and VERIFIED, and have effective
and final availability clocks at or before fit cutoff. The state cannot be
available before its cutoff. Every sample's source lineage is recursively audited.
For STANDARDIZE, parameters must be finite numeric mean and strictly positive
stddev. The supplied fixture values are accepted as supplied statistics; AFRE-1
does not attest they were estimated correctly or calculate them from full data.

A standardized computation requires both state availability and fit cutoff <=
origin information cutoff. Result availability cannot precede raw input or state.
The result/spec/receipt pins state identity. Changed mean/stddev produces a new
state, spec and vintage fingerprint. A future-fitted state cannot normalize an
earlier row. Exact state revisions may share unchanged feature computation logic;
changing the computation itself requires a definition revision.

AFRE-4 owns fold-local fitting, imputation and preprocessing with leakage-safe
splits. No full-dataset scaling, automatic normalization fitting, model fitting
or train/test preprocessing is implemented here. Qualified historical source
reconstruction still preserves later physical clocks and requires delivery
evidence; an archive's publication date cannot backdate a normalization input.
