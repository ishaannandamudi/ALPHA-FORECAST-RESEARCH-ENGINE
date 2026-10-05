"""Independent exact references and fail-closed symmetric PSD diagnostics."""

from dataclasses import replace

import pytest

from afre.multihorizon import Denominator
from afre.multihorizon.covariance import empirical_covariance, validate_psd
from afre.schema import ContractError
from examples.calibration_demo import corrected_calibration_truth
from examples.multihorizon_demo import backbone_spec
from tests.multihorizon.conftest import Case


@pytest.mark.parametrize(
    "denominator, expected", [(Denominator.POPULATION, 2 / 3), (Denominator.SAMPLE, 1.0)]
)
def test_known_covariance(denominator: Denominator, expected: float) -> None:
    mean, matrix = empirical_covariance(((1.0, 2.0), (2.0, 4.0), (3.0, 6.0)), denominator)
    assert mean == (2.0, 4.0)
    assert matrix[0] == pytest.approx((expected, 2 * expected))
    assert matrix[1] == pytest.approx((2 * expected, 4 * expected))
    validate_psd(matrix, 1e-12)


@pytest.mark.parametrize(
    "matrix",
    [
        ((1.0, 0.0), (0.0, 1.0)),
        ((0.0, 0.0), (0.0, 0.0)),
        ((1.0, 1.0), (1.0, 1.0)),
        ((1.0, -1.0), (-1.0, 1.0)),
        ((0.0, 0.0), (0.0, 2.0)),
    ],
)
def test_psd_accepts_degenerate(matrix: tuple[tuple[float, ...], ...]) -> None:
    validate_psd(matrix, 1e-12)


@pytest.mark.parametrize(
    "matrix",
    [
        (),
        ((1.0, 0.0),),
        ((-1.0,),),
        ((1.0, 0.5), (0.4, 1.0)),
        ((1.0, 2.0), (2.0, 1.0)),
        ((0.0, 1.0), (1.0, 1.0)),
        ((float("inf"),),),
    ],
)
def test_invalid_covariance(matrix: tuple[tuple[float, ...], ...]) -> None:
    with pytest.raises(ContractError):
        validate_psd(matrix, 1e-12)


def test_covariance_cutoff_and_heldout_invariance(case: Case) -> None:
    covariance = case.engine.fit_dependence(case.fixture.run.fingerprint, 40, 55)
    assert all(r.origin.timestamp_ns <= 20 for r in covariance.rows)
    old = case.engine.fit_dependence(case.fixture.run.fingerprint, 25, 55)
    assert all(r.origin.timestamp_ns == 10 for r in old.rows)
    raw = case.fixture.tests[1][0]
    from afre.research_datasets.samples import ResearchSample

    sample = case.repo.get(ResearchSample, raw.input.sample_id or "")
    corrected_calibration_truth(case.repo, sample.target_id or "", 110, 100.0)
    assert case.engine.fit_dependence(case.fixture.run.fingerprint, 40, 55) == covariance
    shared = case.engine.fit(backbone_spec(case.fixture), 55, 55, 55)
    assert (
        case.engine.fit_dependence(shared.fingerprint, 40, 55).fit_run_id == shared.fingerprint
    )
    with pytest.raises(ContractError):
        case.engine.fit_dependence(case.fixture.run.fingerprint, 5, 55)
    with pytest.raises(ContractError):
        case.engine.fit_dependence(case.fixture.run.fingerprint, 40, 54)
    with pytest.raises(ContractError):
        replace(covariance, matrix=((1.0, 2.0), (2.0, 1.0)))
    with case.repo.transaction(), pytest.raises(ContractError, match="contamination"):
        case.repo.put(replace(covariance, means=(1.0, 1.0)))


def test_covariance_denominator_rejects_one_row() -> None:
    with pytest.raises(ContractError):
        empirical_covariance(((1.0,),), Denominator.SAMPLE)
    with pytest.raises(ContractError):
        empirical_covariance(((1.0,), (1.0, 2.0)), Denominator.POPULATION)


def test_covariance_ownership_is_explicit(case: Case) -> None:
    from afre.multihorizon import ParameterOwnership

    covariance = case.engine.fit_dependence(case.fixture.run.fingerprint, 40, 55)
    assert covariance.ownership is ParameterOwnership.GLOBAL_SHARED
    with pytest.raises(ContractError):
        replace(covariance, ownership=ParameterOwnership.HORIZON_SPECIFIC)
