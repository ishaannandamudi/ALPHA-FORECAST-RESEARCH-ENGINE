"""Source/estimator clocks, truth guards, frozen TRAIN estimates and explicit TEST access."""

from dataclasses import replace
from typing import TypeVar
from unittest.mock import patch

import pytest

from afre.schema import Artifact, ContractError
from afre.statistical_models.artifacts import DesignMatrix
from afre.target_engine.models import TargetVintage
from afre.uncertainty import ParameterUncertaintySpec, UncertaintySpec
from tests.uncertainty.conftest import Case

A = TypeVar("A", bound=Artifact)


@pytest.mark.parametrize(
    "name",
    [
        "gaussian",
        "empirical",
        "calibrated",
        "event",
        "hard-regime",
        "soft-regime",
        "mixture",
        "nonlinear",
        "tree",
        "sequence",
        "point",
    ],
)
def test_application_no_truth_or_training(case: Case, name: str) -> None:
    d = case.result(name)
    spec = case.repo.get(UncertaintySpec, d.spec_id)
    get = case.repo.get

    def denied(cls: type[A], identity: str) -> A:
        if cls is TargetVintage or cls is DesignMatrix:
            raise AssertionError("forecast-time truth/training read")
        return get(cls, identity)

    with patch.object(case.repo, "get", denied):
        assert case.engine.decompose(spec, 60) == d


def test_guard_cannot_bypass_cached_targets(case: Case) -> None:
    sample = case.fixture.covariances[0].train_sample_ids[0]
    from afre.research_datasets.samples import ResearchSample

    target_id = case.repo.get(ResearchSample, sample).target_id
    assert target_id is not None
    with case.repo.read_snapshot(), case.repo.validation_cache():
        case.repo.resolve(TargetVintage, target_id)
        case.repo.resolve(DesignMatrix, case.fixture.covariances[0].matrix_id)
        with case.repo.feature_only(), pytest.raises(ContractError, match="truth"):
            case.repo.resolve(TargetVintage, target_id)
        with case.repo.feature_only(), pytest.raises(ContractError, match="truth"):
            case.repo.resolve(DesignMatrix, case.fixture.covariances[0].matrix_id)


@pytest.mark.parametrize("clock", [59, 61, 100])
def test_actual_computation_cannot_backdate(case: Case, clock: int) -> None:
    with pytest.raises(ContractError):
        case.engine.decompose(case.repo.get(UncertaintySpec, case.result().spec_id), clock)


def test_provider_or_reconstruction_timestamp_is_not_availability(case: Case) -> None:
    from afre.probabilistic.artifacts import ProbabilisticForecast
    from afre.uncertainty.sources import source_for

    raw = case.repo.get(ProbabilisticForecast, case.result().forecast_id)
    from afre.probabilistic import ProbabilisticEngine

    late = ProbabilisticEngine(case.repo).predict(raw.model_artifact_id, raw.input, 70)
    # Existing AFRE-6 permits an explicitly late/non-causal historical diagnostic source.
    with pytest.raises(ContractError, match="unavailable"):
        source_for(case.repo, late.fingerprint)
    with pytest.raises(ContractError):
        case.engine.decompose(
            replace(
                case.repo.get(UncertaintySpec, case.result().spec_id),
                forecast_id=late.fingerprint,
            ),
            60,
        )


def test_late_covariance_and_heldout_isolation(case: Case) -> None:
    cov = case.fixture.covariances[0]
    policy = case.repo.get(ParameterUncertaintySpec, cov.spec_id)
    before = case.engine.fit_covariance(policy, 40)
    from afre.research_datasets.schema import Partition

    heldout = {
        s.target_id
        for part in (Partition.VALIDATION, Partition.TEST)
        for s in case.repo.partition_samples(cov.fold_id, part)
    }
    get = case.repo.get

    def denied(cls: type[A], identity: str) -> A:
        if cls is TargetVintage and identity in heldout:
            raise AssertionError("held-out response read during covariance fit")
        return get(cls, identity)

    with patch.object(case.repo, "get", denied):
        assert case.engine.fit_covariance(policy, 40) == before
    late = case.engine.fit_covariance(policy, 70)
    with pytest.raises(ContractError):
        case.engine.decompose(
            replace(
                case.repo.get(UncertaintySpec, case.result().spec_id),
                covariance_id=late.fingerprint,
            ),
            60,
        )
    with pytest.raises(ContractError):
        case.engine.fit_covariance(policy, 39)
    assert not any(
        s in before.train_sample_ids
        for s in (
            p.fingerprint for p in case.repo.partition_samples(cov.fold_id, Partition.TEST)
        )
    )
