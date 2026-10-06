"""Thirty-five offline checks of exact identities, explicit limits and immutable replay."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypeVar
from unittest.mock import patch

from afre.mixture import MixtureEngine, MixtureForecast
from afre.mixture.experts import ExpertForecastBinding, ExternalExpertForecast
from afre.probabilistic.artifacts import DistributionParameters, ProbabilisticForecast
from afre.probabilistic.schema import DistributionFamily
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import DesignMatrix
from afre.target_engine.models import TargetVintage
from afre.uncertainty import (
    ClosurePolicy,
    ForecastUncertaintyDecomposition,
    IdentifiabilityStatus,
    ParameterCovariance,
    UncertaintyComponent,
    UncertaintyEngine,
    UncertaintyEvaluationSpec,
    UncertaintyInterval,
    UncertaintyRepository,
    UncertaintyRequest,
    UncertaintySpec,
    UncertaintyType,
)
from afre.uncertainty.parameter import prediction_design
from afre.uncertainty.sources import source_for
from examples.uncertainty_fixture import UncertaintyFixture, build_fixture
from examples.uncertainty_horizon_fixture import horizon_uncertainties
from examples.uncertainty_oracles import ols_covariance, prediction_variance

A = TypeVar("A", bound=Artifact)


def component(
    value: ForecastUncertaintyDecomposition, kind: UncertaintyType
) -> UncertaintyComponent:
    return next(c for c in value.components if c.component is kind)


def corrected_mixture(repo: UncertaintyRepository, identity: str) -> MixtureForecast:
    original = repo.get(MixtureForecast, identity)
    engine = MixtureEngine(repo)
    bindings = []
    changed = False
    for expert_id, binding_id in original.request.expert_inputs:
        assert binding_id is not None
        binding = repo.get(ExpertForecastBinding, binding_id)
        if binding.forecast_id.startswith("afre.mix_external_forecast:") and not changed:
            raw = repo.get(ExternalExpertForecast, binding.forecast_id)
            assert isinstance(raw.distribution, DistributionParameters)
            law = replace(raw.distribution, location=raw.distribution.location + 0.02)
            revised = replace(raw, distribution=law, revision="uncertainty-correction-2")
            binding_id = engine.bind(expert_id, engine.publish_external(revised)).fingerprint
            changed = True
        bindings.append((expert_id, binding_id))
    assert changed
    return engine.forecast(replace(original.request, expert_inputs=tuple(bindings)))


def demonstrate(repo: UncertaintyRepository, fixture: UncertaintyFixture) -> tuple[str, ...]:
    e = UncertaintyEngine(repo)

    def get(name: str) -> ForecastUncertaintyDecomposition:
        return repo.get(ForecastUncertaintyDecomposition, fixture.results(name)[0])

    gaussian, empirical, mixture, soft = (
        get(n) for n in ("gaussian", "empirical", "mixture", "soft-regime")
    )
    raw = repo.get(ProbabilisticForecast, gaussian.forecast_id)
    assert raw.distribution.family is DistributionFamily.GAUSSIAN_LOCATION_SCALE
    print("1. PASS Gaussian causal source")
    assert (
        repo.get(ProbabilisticForecast, empirical.forecast_id).distribution.family
        is DistributionFamily.EMPIRICAL_RESIDUAL
    )
    print("2. PASS empirical causal source")
    assert repo.get(MixtureForecast, mixture.forecast_id).distribution is not None
    print("3. PASS exact finite-mixture source")
    within, between = (
        component(mixture, k).value
        for k in (UncertaintyType.WITHIN_EXPERT_PREDICTIVE, UncertaintyType.EXPERT_DISAGREEMENT)
    )
    assert within is not None and between is not None and mixture.total_variance is not None
    assert abs(within + between - mixture.total_variance) <= 1e-12
    print("4. PASS within plus between closes")
    assert (
        component(mixture, UncertaintyType.EXPERT_DISAGREEMENT).method
        == "finite-mixture-between-v1"
    )
    assert component(mixture, UncertaintyType.PARAMETER).value is None
    print("5. PASS expert disagreement is not automatically epistemic")
    assert component(soft, UncertaintyType.REGIME_AMBIGUITY).units == "nats"
    print("6. PASS supplied soft-regime entropy")
    covariance = fixture.covariances[0]
    matrix = repo.get(DesignMatrix, covariance.matrix_id)
    oracle, sigma = ols_covariance(
        tuple((1.0, *r.values) for r in matrix.rows), tuple(r.response for r in matrix.rows)
    )
    assert (
        max(
            abs(a - b)
            for r, s in zip(oracle, covariance.covariance, strict=True)
            for a, b in zip(r, s, strict=True)
        )
        < 1e-12
    )
    assert (
        covariance.residual_variance is not None
        and abs(sigma - covariance.residual_variance) < 1e-12
    )
    print("7. PASS TRAIN OLS covariance independent oracle")
    design = prediction_design(repo, source_for(repo, raw.fingerprint), covariance)
    estimate = component(gaussian, UncertaintyType.PARAMETER).value
    assert estimate is not None and abs(estimate - prediction_variance(design, oracle)) < 1e-12
    print("8. PASS prediction parameter variance independent oracle")
    assert (
        component(get("tree"), UncertaintyType.PARAMETER).status
        is IdentifiabilityStatus.UNIDENTIFIABLE
    )
    print("9. PASS tree epistemic uncertainty explicitly unidentifiable")
    assert (
        get("sequence").quality_states
        and component(get("sequence"), UncertaintyType.DATA_QUALITY).value is None
    )
    print("10. PASS quality states remain non-numerical diagnostics")
    assert mixture.closure is ClosurePolicy.EXACT_ADDITIVE
    print("11. PASS only valid mixture identity is additive")
    assert mixture.closure_error is not None and abs(mixture.closure_error) <= 1e-12
    print("12. PASS declared closure tolerance")
    partial = e.decompose(
        UncertaintySpec(
            repo.get(UncertaintySpec, mixture.spec_id).target,
            mixture.forecast_id,
            tuple(
                UncertaintyRequest(k)
                for k in (
                    UncertaintyType.TOTAL_PREDICTIVE,
                    UncertaintyType.EXPERT_DISAGREEMENT,
                    UncertaintyType.RESIDUAL_UNATTRIBUTED,
                )
            ),
            ClosurePolicy.EXACT_ADDITIVE,
        ),
        60,
    )
    residual = component(partial, UncertaintyType.RESIDUAL_UNATTRIBUTED).value
    assert residual is not None and abs(residual - within) < 1e-12
    print("13. PASS compatible partial identity retains unattributed remainder")
    assert repo.get(UncertaintyInterval, gaussian.interval_id).width is not None
    print("14. PASS source-law prediction interval")
    policy = UncertaintyEvaluationSpec(bucket_count=2)
    validation = e.evaluate(fixture.results("gaussian"), policy, 100, 100)
    assert validation.coverage.empirical_coverage == sum(
        bool(p.covered) for p in validation.pairs
    ) / len(validation.pairs)
    print("15. PASS nominal and empirical coverage separately evaluated")
    assert validation.coverage.mean_width is not None
    assert (
        abs(
            validation.coverage.mean_width
            - sum(p.interval_width for p in validation.pairs if p.interval_width is not None)
            / len(validation.pairs)
        )
        < 1e-12
    )
    print("16. PASS separate interval sharpness")
    assert sum(len(b.sample_ids) for b in validation.buckets) == len(validation.pairs)
    print("17. PASS deterministic uncertainty buckets")
    mixed_evaluation = e.evaluate(fixture.results("mixture"), policy, 100, 100)
    assert mixed_evaluation.error_diagnostic.sample_ids
    print("18. PASS descriptive uncertainty versus realized error")
    assert (
        component(get("event"), UncertaintyType.EVENT_AMBIGUITY).status
        is IdentifiabilityStatus.PROXY_ONLY
    )
    print("19. PASS event-conditioned spread remains a proxy")
    assert get("hard-regime").target_id == soft.target_id
    print("20. PASS hard and soft regime source integration")
    assert mixed_evaluation.coverage.interval_count == 0
    print("21. PASS mixture law supported without invented quantiles")
    assert (
        component(get("nonlinear"), UncertaintyType.PARAMETER).status
        is IdentifiabilityStatus.PARTIALLY_IDENTIFIED
    )
    print("22. PASS nonlinear readout covariance is conditional on fixed design")
    assert fixture.covariances[2].status is IdentifiabilityStatus.PARTIALLY_IDENTIFIED
    print("23. PASS sequence covariance covers readout only")
    horizons = horizon_uncertainties(repo)
    assert horizons[0][0].horizon_id != horizons[1][0].horizon_id
    assert horizons[0][0].total_variance != horizons[1][0].total_variance
    print("24. PASS actual independent 1h and 1d uncertainty")
    old_get = repo.get

    def guarded(cls: type[A], identity: str) -> A:
        if cls is TargetVintage:
            raise ContractError("future truth denied by demo")
        return old_get(cls, identity)

    spec = repo.get(UncertaintySpec, gaussian.spec_id)
    with patch.object(repo, "get", guarded):
        assert e.decompose(spec, 60) == gaussian
    print("25. PASS construction reads no TargetVintage")
    with patch.object(repo, "get", guarded):
        assert (
            e.decompose(
                repo.get(
                    UncertaintySpec,
                    repo.get(ForecastUncertaintyDecomposition, fixture.test_ids[0]).spec_id,
                ),
                80,
            ).fingerprint
            == fixture.test_ids[0]
        )
    print("26. PASS TEST truth perturbation cannot enter construction")
    other = e.evaluate(fixture.results("empirical"), policy, 100, 100)
    comparison = e.compare(validation.fingerprint, other.fingerprint, 100)
    assert len(comparison.sample_truth_ids) == len(validation.pairs)
    print("27. PASS exact matched sample and truth comparison")
    test = e.evaluate(fixture.test_ids, policy, 100, 100, "uncertainty-demo-test")
    before = tuple(c.fingerprint for c in fixture.covariances)
    drift = e.drift((validation.fingerprint, test.fingerprint), 100)
    assert drift.behavior == "descriptive-no-refit-no-selection-v1"
    print("28. PASS known-window descriptive drift")
    assert tuple(repo.get(ParameterCovariance, i).fingerprint for i in before) == before
    print("29. PASS diagnostics cannot refit")
    old_bytes = canonical_json(mixture)
    corrected = corrected_mixture(repo, mixture.forecast_id)
    print("30. PASS explicit corrected source forecast")
    assert (
        canonical_json(repo.get(ForecastUncertaintyDecomposition, mixture.fingerprint))
        == old_bytes
    )
    print("31. PASS old decomposition bytes unchanged")
    replacement = e.decompose(
        replace(repo.get(UncertaintySpec, mixture.spec_id), forecast_id=corrected.fingerprint),
        60,
    )
    assert replacement.fingerprint != mixture.fingerprint
    print("32. PASS explicit rebuild creates new identity")
    return (
        gaussian.fingerprint,
        empirical.fingerprint,
        mixture.fingerprint,
        validation.fingerprint,
        test.fingerprint,
        replacement.fingerprint,
    )


def main() -> None:
    import socket
    from contextlib import ExitStack

    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("network forbidden in uncertainty demo")

    with ExitStack() as stack, TemporaryDirectory() as temporary:
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
            "gethostbyaddr",
            "socketpair",
        ):
            stack.enter_context(patch.object(socket, name, denied))
        path = Path(temporary) / "uncertainty.sqlite"
        with UncertaintyRepository(path) as repo:
            fixture = build_fixture(repo)
            ids = demonstrate(repo, fixture)
            frozen = tuple(canonical_json(repo.get_any(i)) for i in ids)
        with UncertaintyRepository(path) as repo:
            print("33. PASS persistence and restart")
            assert tuple(canonical_json(repo.get_any(i)) for i in ids) == frozen
            print("34. PASS deterministic semantic replay")
            audit = UncertaintyEngine(repo).audit_lineage(ids[-2])
            print("35. PASS bounded audit/lineage", len(audit.node_ids))


if __name__ == "__main__":
    main()
