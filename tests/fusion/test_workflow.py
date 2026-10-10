"""Causal fixed/learned application, isolation and explicit missingness."""

from dataclasses import replace
from math import fsum

import pytest

from afre.fusion import (
    ExternalFusionOutput,
    FusedForecast,
    FusionArtifact,
    FusionEngine,
    FusionFamily,
    FusionIntercept,
    FusionMissingness,
    FusionNormalization,
    FusionObservation,
    FusionRepository,
    FusionStatus,
    FusionWeights,
)
from afre.fusion.application import forecast_for
from afre.fusion.guards import train_only
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.target_engine.models import TargetVintage
from examples.fusion_fixture import FusionFixture, apply_partition

Case = tuple[FusionRepository, FusionFixture]


def learned(repo: FusionRepository, fixture: FusionFixture) -> FusionArtifact:
    spec = replace(
        fixture.spec,
        name="learned",
        family=FusionFamily.LEARNED_LINEAR_POINT,
        weight_policy=FusionWeights.UNCONSTRAINED_QR,
        weights=(),
        intercept_policy=FusionIntercept.WITH_INTERCEPT,
    )
    return FusionEngine(repo).fit(
        spec, 40, 40, 40, tuple((i, fixture.observations(i)) for i in fixture.train)
    )


def test_fixed_contributions_and_target_free(
    fusion_case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    spec = replace(
        f.spec, fixed_intercept=0.75, intercept_policy=FusionIntercept.WITH_INTERCEPT
    )
    artifact = e.fit(spec, 0, 0, 0)
    sample = repo.get(ResearchSample, f.validation[0])
    original_get = repo.get
    reads = []

    def audited_get(cls: type[TargetVintage], identity: str) -> TargetVintage:
        if cls is TargetVintage:
            reads.append(identity)
            raise AssertionError("application read target truth")
        return original_get(cls, identity)

    monkeypatch.setattr(repo, "get", audited_get)
    forecast = e.apply(
        artifact.fingerprint, sample.fingerprint, f.observations(sample.fingerprint), 40
    )
    assert not reads
    obs = tuple(repo.get(FusionObservation, i) for i in f.observations(sample.fingerprint))
    assert forecast.value == fsum(0.5 * o.value for o in obs if o.value is not None) + 0.75
    assert (
        forecast.value
        == fsum(
            c.weighted_value for c in forecast.contributions if c.weighted_value is not None
        )
        + artifact.intercept
    )
    assert forecast.available_ns == 40
    assert (
        e.apply(
            artifact.fingerprint,
            sample.fingerprint,
            tuple(reversed(f.observations(sample.fingerprint))),
            40,
        )
        == forecast
    )
    with pytest.raises(ContractError, match="mandatory target-free"):
        forecast_for(repo, artifact.fingerprint, sample.fingerprint, (), 40)


def test_learned_oracle_and_heldout_isolation(
    fusion_case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, f = fusion_case
    artifact = learned(repo, f)
    expected = {r.fingerprint: 5.0 if r.source_id.endswith("-0") else 0.0 for r in f.references}
    assert max(abs(w - expected[i]) for i, w in artifact.weights) < 1e-10
    assert abs(artifact.intercept) < 1e-12
    assert artifact.rank == 3 and artifact.condition_proxy is not None
    heldout = {repo.get(ResearchSample, i).target_id for i in (*f.validation, *f.test)}
    original_get = repo.get

    def perturbed(cls: type[TargetVintage], identity: str) -> TargetVintage:
        value = original_get(cls, identity)
        if cls is TargetVintage and identity in heldout:
            raise AssertionError("held-out truth reached TRAIN fit")
        return value

    monkeypatch.setattr(repo, "get", perturbed)
    assert learned(repo, f) == artifact
    forecasts = apply_partition(repo, f, artifact.fingerprint, f.validation)
    for i in forecasts:
        forecast = repo.get(FusedForecast, i)
        sample = repo.get(ResearchSample, forecast.sample_id)
        expected_y = 5.0 / (100 + sample.timestamp_ns + int(sample.security.value) - 1)
        assert forecast.value is not None and abs(forecast.value - expected_y) < 1e-12
    target_id = repo.get(ResearchSample, f.validation[0]).target_id
    assert target_id is not None
    with repo.read_snapshot(), repo.validation_cache(), train_only(repo, ()):
        for call in (repo.get, repo.resolve):
            with pytest.raises(ContractError, match="TRAIN guard"):
                call(TargetVintage, target_id)
        with pytest.raises(ContractError, match="TRAIN guard"):
            repo.get_any(target_id)


@pytest.mark.parametrize("policy", tuple(FusionMissingness))
def test_fixed_missingness(fusion_case: Case, policy: FusionMissingness) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    spec = (
        replace(f.spec, missingness=policy)
        if policy is not FusionMissingness.USE_DECLARED_FALLBACK
        else f.spec
    )
    fallback_id = None
    if policy is FusionMissingness.USE_DECLARED_FALLBACK:
        definition = replace(f.definitions[0], logical_id="fallback")
        sample = repo.get(ResearchSample, f.validation[0])
        assert sample.origin is not None
        from afre.feature_store.models import AvailabilityEvidence

        output = ExternalFusionOutput(
            definition.fingerprint,
            sample.fingerprint,
            sample.origin,
            0.2,
            None,
            AvailabilityEvidence(40, 40, 40, 40),
            "fallback",
        )
        e.external(definition, (output,))
        ref = e.source(output.fingerprint)
        spec = replace(f.spec, missingness=policy, fallback_source_id=ref.fingerprint)
        fallback_id = e.observe(ref.fingerprint, output.fingerprint).fingerprint
    artifact = e.fit(spec, 0, 0, 0)
    one = f.observations(f.validation[0])[:1]
    forecast = e.apply(artifact.fingerprint, f.validation[0], one, 40, fallback_id)
    if policy is FusionMissingness.FAIL:
        assert forecast.value is None and forecast.status is FusionStatus.UNAVAILABLE
    elif policy is FusionMissingness.DROP_AND_RENORMALIZE:
        assert forecast.value == repo.get(FusionObservation, one[0]).value
        assert sum(c.effective_weight for c in forecast.contributions) == 1.0
    else:
        assert forecast.value == 0.2 and forecast.reason == "declared-fallback"


def test_learned_missing_cannot_delete_columns(fusion_case: Case) -> None:
    repo, f = fusion_case
    artifact = learned(repo, f)
    result = FusionEngine(repo).apply(
        artifact.fingerprint, f.validation[0], f.observations(f.validation[0])[:1], 40
    )
    assert result.status is FusionStatus.UNAVAILABLE and result.value is None
    with pytest.raises(ContractError, match="fixed simplex"):
        replace(
            f.spec,
            family=FusionFamily.LEARNED_LINEAR_POINT,
            weights=(),
            weight_policy=FusionWeights.UNCONSTRAINED_QR,
            missingness=FusionMissingness.DROP_AND_RENORMALIZE,
        )


def test_explicit_normalization(fusion_case: Case) -> None:
    repo, f = fusion_case
    spec = replace(
        f.spec,
        weights=tuple((i, w * 8) for i, w in f.spec.weights),
        normalization=FusionNormalization.EXPLICIT_SIMPLEX,
    )
    artifact = FusionEngine(repo).fit(spec, 0, 0, 0)
    assert artifact.weights == f.spec.weights and artifact.spec_id != f.spec.fingerprint
    with pytest.raises(ContractError, match="weight sum"):
        replace(spec, normalization=FusionNormalization.NONE)


def test_fit_boundaries_and_late_artifact(fusion_case: Case) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    spec = replace(
        f.spec,
        family=FusionFamily.LEARNED_LINEAR_POINT,
        weight_policy=FusionWeights.UNCONSTRAINED_QR,
        weights=(),
    )
    with pytest.raises(ContractError, match="TRAIN grid"):
        e.fit(spec, 40, 40, 40, tuple((i, f.observations(i)) for i in f.validation))
    with pytest.raises(ContractError, match="exact fit cutoff"):
        e.fit(spec, 100, 100, 100, ())
    late = e.fit(f.spec, 0, 60, 60)
    with pytest.raises(ContractError, match="unavailable at use origin"):
        e.apply(late.fingerprint, f.validation[0], f.observations(f.validation[0]), 40)


def test_corrected_source_has_new_output_identity(fusion_case: Case) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    artifact = e.fit(f.spec, 0, 0, 0)
    sample_id = f.validation[0]
    old = e.apply(artifact.fingerprint, sample_id, f.observations(sample_id), 40)
    frozen = canonical_json(old)
    obs = repo.get(FusionObservation, f.observations(sample_id)[0])
    raw = repo.get(ExternalFusionOutput, obs.output_id)
    corrected = replace(raw, value=999.0, revision="corrected")
    from afre.fusion.external import ExternalFusionDefinition

    e.external(repo.get(ExternalFusionDefinition, raw.definition_id), (corrected,))
    new_obs = e.observe(obs.source_id, corrected.fingerprint)
    ids = tuple(
        new_obs.fingerprint if i == obs.fingerprint else i for i in f.observations(sample_id)
    )
    new = e.apply(artifact.fingerprint, sample_id, ids, 40)
    assert new.fingerprint != old.fingerprint and new.value != old.value
    assert canonical_json(repo.resolve(FusedForecast, old.fingerprint)) == frozen


def test_target_free_replay_rejects_forged_source_witness(fusion_case: Case) -> None:
    repo, f = fusion_case
    artifact = learned(repo, f)
    row = artifact.rows[0]
    forged = replace(
        artifact,
        rows=(replace(row, values=(row.values[0] + 1.0, *row.values[1:])), *artifact.rows[1:]),
    )
    with repo.feature_only(), pytest.raises(ContractError, match="source/TRAIN witness"):
        FusionEngine(repo)._publish((forged,))
    with repo.feature_only(), pytest.raises(ContractError, match="exact cutoff"):
        FusionEngine(repo)._publish((replace(artifact, fit_cutoff_ns=39),))


def test_no_post_validation_test_choice_without_afre20(fusion_case: Case) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    artifact = e.fit(f.spec, 0, 0, 0)
    with pytest.raises(ContractError, match="before held-out outcomes"):
        e.choose_test(artifact.fingerprint, 50, "post-validation winner")
