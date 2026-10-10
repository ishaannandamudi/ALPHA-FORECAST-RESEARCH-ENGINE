"""Independent analytic Gaussian/empirical mixture and proper-score oracles."""

from dataclasses import replace
from math import erf, exp, fsum, log, pi, sqrt

import pytest

from afre.fusion import (
    ExternalFusionDefinition,
    ExternalFusionOutput,
    FusionEngine,
    FusionRepository,
    FusionWeights,
)
from afre.fusion.probabilistic import (
    FusionDistribution,
    blend,
    crps,
    mean,
    mixture_cdf,
    nll,
    quantile,
    threshold_probability,
    variance_parts,
)
from afre.probabilistic.artifacts import DistributionParameters, QuantileValue
from afre.probabilistic.schema import DistributionFamily
from afre.schema import ContractError
from examples.fusion_fixture import FusionFixture
from examples.fusion_probabilities import probability_fixture

Case = tuple[FusionRepository, FusionFixture]


def test_gaussian_mixture_oracle(fusion_case: Case) -> None:
    repo, f = fusion_case
    spec, ids = probability_fixture(repo, f)
    engine = FusionEngine(repo)
    artifact = engine.fit(spec, 0, 0, 0)
    forecast = engine.apply(artifact.fingerprint, f.validation[0], ids, 40)
    law = forecast.law
    assert isinstance(law, FusionDistribution) and len(law.components) == 2
    assert mean(law) == 2.0
    within, between = variance_parts(law)
    assert within == 1.1875 and between == 3.0
    expected_cdf = 0.25 * (0.5 + 0.5 * erf(0.5 / sqrt(2))) + 0.75 * (
        0.5 + 0.5 * erf(-6 / sqrt(2))
    )
    assert abs(mixture_cdf(law, 0.0) - expected_cdf) < 1e-15
    assert abs(threshold_probability(law, 0.0) - (1 - expected_cdf)) < 1e-15
    density = 0.25 * exp(-0.5 * (1 / 2) ** 2) / (sqrt(2 * pi) * 2) + 0.75 * exp(
        -0.5 * (3 / 0.5) ** 2
    ) / (sqrt(2 * pi) * 0.5)
    score = nll(law, 0.0)
    assert score is not None and abs(score + log(density)) < 1e-14
    with pytest.raises(ContractError, match="quantiles unavailable"):
        quantile(law, 0.5)


def test_empirical_mixture_weighted_atoms(fusion_case: Case) -> None:
    repo, f = fusion_case
    spec, ids = probability_fixture(repo, f, True)
    engine = FusionEngine(repo)
    artifact = engine.fit(spec, 0, 0, 0)
    law = engine.apply(artifact.fingerprint, f.validation[0], ids, 40).law
    assert law is not None
    atoms = ((-2.0, 0.125), (0.0, 0.125), (2.0, 0.375), (4.0, 0.375))
    assert mean(law) == fsum(x * w for x, w in atoms)
    assert mixture_cdf(law, 0.0) == 0.25 and threshold_probability(law, 0.0) == 0.75
    assert sum(variance_parts(law)) == fsum(w * (x - 2.0) ** 2 for x, w in atoms)
    expected = fsum(w * abs(x - 1.0) for x, w in atoms) - 0.5 * fsum(
        w * v * abs(x - y) for x, w in atoms for y, v in atoms
    )
    assert crps(law, 1.0) == expected and nll(law, 1.0) is None
    with pytest.raises(ContractError, match="CRPS work bound"):
        crps(law, 1.0, 1)


def test_quantile_only_is_incompatible(fusion_case: Case) -> None:
    repo, f = fusion_case
    spec, ids = probability_fixture(repo, f)
    from afre.fusion import FusionObservation

    obs = repo.get(FusionObservation, ids[0])
    raw = repo.get(ExternalFusionOutput, obs.output_id)
    law = DistributionParameters(
        DistributionFamily.QUANTILE_SET,
        0.0,
        1.0,
        quantile_values=(
            QuantileValue(0.1, -1.0),
            QuantileValue(0.5, 0.0),
            QuantileValue(0.9, 1.0),
        ),
    )
    replacement = replace(raw, value=0.0, law=law, revision="quantile-only")
    e = FusionEngine(repo)
    e.external(repo.get(ExternalFusionDefinition, raw.definition_id), (replacement,))
    new = e.observe(obs.source_id, replacement.fingerprint)
    artifact = e.fit(spec, 0, 0, 0)
    with pytest.raises(ContractError, match="INCOMPATIBLE"):
        e.apply(artifact.fingerprint, f.validation[0], (new.fingerprint, ids[1]), 40)
    with pytest.raises(ContractError, match="simplex"):
        replace(spec, weights=tuple((i, -w) for i, w in spec.weights))


def test_component_bound_and_zero_weight(fusion_case: Case) -> None:
    repo, f = fusion_case
    spec, ids = probability_fixture(repo, f)
    from afre.fusion import FusionObservation

    obs = tuple(repo.get(FusionObservation, i) for i in ids)
    assert all(o.law is not None for o in obs)
    with pytest.raises(ContractError, match="component bound"):
        blend(
            tuple((o.source_id, o.output_id, 0.5, o.law) for o in obs if o.law is not None), 1
        )
    law = blend(
        tuple(
            (o.source_id, o.output_id, float(j), o.law)
            for j, o in enumerate(obs)
            if o.law is not None
        ),
        2,
    )
    assert len(law.components) == 1
    with pytest.raises(ContractError, match="intercept"):
        replace(spec, fixed_intercept=1.0)
    assert spec.weight_policy is FusionWeights.SIMPLEX
