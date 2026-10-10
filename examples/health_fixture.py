"""Known frozen point/Gaussian vectors on the native AFRE4 sample grid."""

from dataclasses import dataclass, replace

from afre.feature_store.models import AvailabilityEvidence
from afre.fusion import (
    ExternalFusionDefinition,
    ExternalFusionOutput,
    FusionEngine,
    FusionFamily,
    FusionKind,
)
from afre.health import (
    HealthDiagnostic,
    HealthDiagnosticRequest,
    HealthDirection,
    HealthEngine,
    HealthRepository,
    HealthRule,
    HealthSpec,
    HealthStatistic,
    MonitoredArtifactReference,
    MonitoringWindow,
)
from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.schema import DistributionFamily
from afre.research_datasets.samples import ResearchSample
from examples.feature_store_demo import SOURCE
from examples.fusion_fixture import FusionFixture, build_fixture


@dataclass(frozen=True)
class HealthFixture:
    upstream: FusionFixture
    artifact_id: str
    reference: MonitoredArtifactReference
    observation_ids: tuple[str, ...]
    input_ids: tuple[str, ...]
    output_ids: tuple[str, ...]
    probability_reference: MonitoredArtifactReference
    probability_ids: tuple[str, ...]


def build_health_fixture(repo: HealthRepository, reverse: bool = False) -> HealthFixture:
    upstream = build_fixture(repo, reverse)
    engine = FusionEngine(repo)
    health = HealthEngine(repo)
    samples = tuple(
        repo.get(ResearchSample, i)
        for i in (*upstream.train, *upstream.validation, *upstream.test)
    )
    target = upstream.definitions[0].target
    references = []
    observations = []
    outputs = []
    artifacts = []
    for probabilistic in (False, True):
        definition = ExternalFusionDefinition(
            "health-known-" + str(probabilistic),
            SOURCE.provenance.system,
            "1",
            target,
            FusionKind.PROBABILISTIC if probabilistic else FusionKind.POINT,
            "target-value:" + target.fingerprint,
            SOURCE,
            0,
        )
        raw = []
        for sample in reversed(samples) if reverse else samples:
            assert sample.origin is not None
            index = int(sample.security.value)
            value = float(index + (3 if sample.timestamp_ns >= 40 else 0))
            sigma = 2.0 if sample.timestamp_ns >= 40 else 1.0
            law = (
                DistributionParameters(DistributionFamily.GAUSSIAN_LOCATION_SCALE, value, sigma)
                if probabilistic
                else None
            )
            raw.append(
                ExternalFusionOutput(
                    definition.fingerprint,
                    sample.fingerprint,
                    sample.origin,
                    value,
                    law,
                    AvailabilityEvidence(
                        sample.timestamp_ns,
                        sample.timestamp_ns,
                        sample.timestamp_ns,
                        sample.timestamp_ns,
                    ),
                    "initial",
                )
            )
        engine.external(definition, tuple(raw))
        ref = engine.source(min(raw, key=lambda r: r.sample_id).fingerprint)
        spec = replace(
            upstream.spec,
            name="known-health-" + str(probabilistic),
            source_ids=(ref.fingerprint,),
            weights=((ref.fingerprint, 1.0),),
            kind=definition.kind,
            family=FusionFamily.FIXED_PROBABILITY_MIXTURE
            if probabilistic
            else FusionFamily.FIXED_WEIGHT_POINT,
        )
        artifact = engine.fit(spec, 0, 0, 0)
        engine.choose_test(artifact.fingerprint, 0, "single-predeclared-health-fixture")
        artifacts.append(artifact.fingerprint)
        produced = []
        for row in raw:
            obs = engine.observe(ref.fingerprint, row.fingerprint)
            produced.append(
                engine.apply(
                    artifact.fingerprint,
                    row.sample_id,
                    (obs.fingerprint,),
                    row.origin.timestamp_ns,
                )
            )
        monitor = health.monitor(artifact.fingerprint)
        references.append(monitor)
        observations.append(
            tuple(
                sorted(
                    health.observe(monitor.fingerprint, o.fingerprint, 120).fingerprint
                    for o in produced
                )
            )
        )
        outputs.append(tuple(sorted(o.fingerprint for o in produced)))
    inputs = []
    for sample in samples:
        assert sample.join_id is not None
        inputs.append(
            health.input(
                references[0].fingerprint, sample.join_id, sample.fingerprint, 120
            ).fingerprint
        )
    return HealthFixture(
        upstream,
        artifacts[0],
        references[0],
        observations[0],
        tuple(sorted(inputs)),
        outputs[0],
        references[1],
        observations[1],
    )


def health_spec(
    repo: HealthRepository,
    fixture: HealthFixture,
    kinds: tuple[HealthDiagnostic, ...],
    probability: bool = False,
    input_column: str | None = None,
    reference_start: int = 10,
    current_start: int = 40,
    minimum: int = 2,
    cutoff_ns: int = 120,
) -> tuple[HealthSpec, tuple[HealthRule, ...]]:
    from afre.health import HealthObservation

    ids = (
        fixture.input_ids
        if input_column
        else fixture.probability_ids
        if probability
        else fixture.observation_ids
    )
    reference_window = MonitoringWindow(
        "reference", reference_start, reference_start + 1, cutoff_ns, minimum
    )
    current_window = MonitoringWindow(
        "current", current_start, current_start + 1, cutoff_ns, minimum
    )
    requests = tuple(
        HealthDiagnosticRequest(k, input_column or "prediction", minimum) for k in kinds
    )
    rules = tuple(
        HealthRule(
            k.value,
            k,
            HealthDirection.HIGHER_WORSE,
            HealthStatistic.DELTA,
            minimum,
            0.5,
            2.0,
            0,
        )
        for k in kinds
    )
    by_kind = {r.kind: r for r in rules}
    spec = HealthSpec(
        "known-health",
        fixture.probability_reference.fingerprint
        if probability
        else fixture.reference.fingerprint,
        fixture.reference.target_id,
        fixture.reference.horizon_id,
        reference_window,
        current_window,
        requests,
        tuple((r.fingerprint, by_kind[r.kind].fingerprint) for r in requests),
        tuple(
            i for i in ids if reference_window.contains(repo.get(HealthObservation, i).valid_ns)
        ),
        tuple(
            i for i in ids if current_window.contains(repo.get(HealthObservation, i).valid_ns)
        ),
        minimum,
        0,
    )
    return spec, rules
