"""Independent law oracles and invalid contracts; sparse quantiles imply no CDF."""

from dataclasses import replace
from math import erf, sqrt
from typing import Any, cast

import pytest

from afre.probabilistic.artifacts import DistributionParameters, QuantileValue
from afre.probabilistic.schema import DistributionFamily
from afre.schema import ContractError
from afre.service import ServiceLawComponent, ServiceProbabilityLaw, canonical_json, deserialize
from afre.service.native import public_law


@pytest.mark.parametrize(
    "comparison,expected", [("GT", 0.25), ("GE", 0.75), ("LT", 0.25), ("LE", 0.75)]
)
def test_empirical_atom_ties(comparison: str, expected: float) -> None:
    native = DistributionParameters(
        DistributionFamily.EMPIRICAL_RESIDUAL, 5.0, 0.0, (-1.0, 0.0, 0.0, 1.0)
    )
    law = public_law(native)
    assert law is not None and law.kind == "EMPIRICAL"
    assert law.components[0].atoms == (4.0, 5.0, 5.0, 6.0)
    assert law.threshold_probability(5.0, comparison) == expected
    assert deserialize(canonical_json(law)) == law


@pytest.mark.parametrize("comparison", ["GT", "GE", "LT", "LE"])
def test_gaussian_oracle(comparison: str) -> None:
    native = DistributionParameters(DistributionFamily.GAUSSIAN_LOCATION_SCALE, 2.0, 3.0)
    law = public_law(native)
    assert law is not None
    expected = (1 + erf(1 / sqrt(2))) / 2
    if comparison in ("GT", "GE"):
        expected = 1 - expected
    assert abs(law.threshold_probability(5.0, comparison) - expected) < 2e-16
    assert (law.components[0].location, law.components[0].scale) == (2.0, 3.0)


def test_mixture_and_quantiles() -> None:
    a = ServiceLawComponent("a", 0.25, "GAUSSIAN", 0.0, 1.0)
    b = ServiceLawComponent("b", 0.75, "EMPIRICAL", 0.0, 0.0, (0.0, 1.0))
    law = ServiceProbabilityLaw("MIXTURE", "native-mixture", (b, a))
    assert law.components == (a, b)
    assert law.threshold_probability(0.0, "GT") == 0.5
    assert law.threshold_probability(0.0, "GE") == 0.875
    assert law.threshold_probability(0.0, "LT") == 0.125
    assert law.threshold_probability(0.0, "LE") == 0.5
    sparse = DistributionParameters(
        DistributionFamily.QUANTILE_SET,
        0.0,
        0.0,
        quantile_values=(
            QuantileValue(0.1, -1.0),
            QuantileValue(0.5, 0.0),
            QuantileValue(0.9, 1.0),
        ),
    )
    projected = public_law(sparse)
    assert projected is not None and projected.kind == "QUANTILES"
    with pytest.raises(ContractError, match="quantile-only"):
        projected.threshold_probability(0.0, "GT")
    assert public_law(None) is None
    for threshold, comparison in ((float("nan"), "GT"), (0.0, "BAD")):
        with pytest.raises(ContractError):
            law.threshold_probability(threshold, comparison)
    for args in (
        ("bad", "x", (a,)),
        ("GAUSSIAN", "x", (a, b)),
        ("MIXTURE", "x", (replace(b, weight=0.7), a)),
        ("MIXTURE", "x", (projected.components[0],)),
    ):
        with pytest.raises(ContractError):
            ServiceProbabilityLaw(*args)


@pytest.mark.parametrize(
    "field,value",
    [
        ("weight", 0.0),
        ("scale", 0.0),
        ("family", "BAD"),
        ("atoms", (1.0,)),
        ("quantiles", ((0.5, 1.0),)),
    ],
)
def test_invalid_component(field: str, value: object) -> None:
    a = ServiceLawComponent("a", 1.0, "GAUSSIAN", 0.0, 1.0)
    with pytest.raises(ContractError):
        replace(a, **{field: cast(Any, value)})


@pytest.mark.parametrize(
    "quantiles", [((0.0, 1.0),), ((0.5, 1.0), (0.5, 2.0)), ((0.1, 2.0), (0.9, 1.0))]
)
def test_quantile_validation(quantiles: tuple[tuple[float, float], ...]) -> None:
    with pytest.raises(ContractError):
        ServiceLawComponent("sparse", 1.0, "QUANTILES", 0.0, 0.0, quantiles=quantiles)


def test_lineage_does_not_treat_labels_as_artifact_references() -> None:
    from afre.service.lineage import reference_ids

    label = "afre.fs_vintage:1.0:" + "a" * 64
    component = ServiceLawComponent(label, 1.0, "EMPIRICAL", 0.0, 0.0, (0.0,))
    assert reference_ids(component) == ()
