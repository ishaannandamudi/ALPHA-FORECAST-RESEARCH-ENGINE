# Expert disagreement uncertainty

For a supplied finite mixture with normalized positive weights w and full component laws, `mu = sum(w_i mu_i)`, `within = sum(w_i Var_i)`, `between = sum(w_i (mu_i−mu)²)`, and `total = within + between`. AFRE-15 reuses AFRE-12 exact law moments; all finite empirical atoms and Gaussian scales retain their native semantics. Experts need not be independent for this mixture identity.

`WITHIN_EXPERT_PREDICTIVE` and `EXPERT_DISAGREEMENT` are mathematical identified terms under this law. Their additive shares require an explicit exact decomposition and positive total. Between-expert variance is not automatically calibrated epistemic variance. Zero total has undefined shares. Unsupported mixture quantiles remain unsupported; no average of component quantiles becomes a mixture quantile.

For point mixtures, weighted point prediction variance and `sum_ij w_i w_j abs(pred_i−pred_j)` are `PROXY_ONLY` and non-additive. Missing/excluded expert reasons and effective availability counts remain quality cohorts. No quality flag becomes a variance increment.

Specification spread requires at least the requested minimum number of distinct supplied models with exact same security, origin, sample, target, fold and partition. Equal weights are explicit. Duplicated model IDs or unmatched samples reject. There is no automatic selection, epistemic posterior or ensemble fitting.

Predictive uncertainty does not establish trading profitability. These are descriptive forecast artifacts; portfolio construction, risk optimization and execution remain downstream projects after AFRE. AFRE-15 has no direct external-engine dependency.
