"""Declared two-source Gaussian or empirical fixture, without target reads."""

from dataclasses import replace

from afre.feature_store.models import AvailabilityEvidence
from afre.fusion import (
    ExternalFusionDefinition,
    ExternalFusionOutput,
    FusionEngine,
    FusionFamily,
    FusionKind,
    FusionRepository,
    FusionSourceReference,
    FusionSpec,
)
from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.schema import DistributionFamily
from afre.research_datasets.samples import ResearchSample
from examples.feature_store_demo import SOURCE
from examples.fusion_fixture import FusionFixture


def probability_fixture(
    repo: FusionRepository, f: FusionFixture, empirical: bool = False
) -> tuple[FusionSpec, tuple[str, ...]]:
    sample = repo.get(ResearchSample, f.validation[0])
    assert sample.origin is not None
    engine = FusionEngine(repo)
    refs: list[FusionSourceReference] = []
    obs = []
    target = f.definitions[0].target
    for j, (mu, sigma) in enumerate(((-1.0, 2.0), (3.0, 0.5))):
        definition = ExternalFusionDefinition(
            "gaussian-" + str(j),
            SOURCE.provenance.system,
            "1",
            target,
            FusionKind.PROBABILISTIC,
            "target-value:" + target.fingerprint,
            SOURCE,
            0,
        )
        law = DistributionParameters(
            DistributionFamily.EMPIRICAL_RESIDUAL
            if empirical
            else DistributionFamily.GAUSSIAN_LOCATION_SCALE,
            mu,
            sigma,
            (-1.0, 1.0) if empirical else (),
        )
        raw = ExternalFusionOutput(
            definition.fingerprint,
            sample.fingerprint,
            sample.origin,
            mu,
            law,
            AvailabilityEvidence(40, 40, 40, 40),
            "1",
        )
        engine.external(definition, (raw,))
        ref = engine.source(raw.fingerprint)
        refs.append(ref)
        obs.append(engine.observe(ref.fingerprint, raw.fingerprint).fingerprint)
    spec = replace(
        f.spec,
        name="exact-mixture",
        source_ids=tuple(r.fingerprint for r in refs),
        family=FusionFamily.FIXED_PROBABILITY_MIXTURE,
        kind=FusionKind.PROBABILISTIC,
        weights=tuple(
            (r.fingerprint, 0.25 if r.source_id.endswith("-0") else 0.75) for r in refs
        ),
    )
    return spec, tuple(obs)
