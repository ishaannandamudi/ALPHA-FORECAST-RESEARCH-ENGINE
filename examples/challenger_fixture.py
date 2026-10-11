"""Known independent causal functions on native research samples; no truth during prediction."""

from dataclasses import dataclass, replace

from afre.challenger import (
    ChallengeDirection,
    ChallengeEngine,
    ChallengeMetric,
    ChallengeMetricRequest,
    ChallengeProgram,
    ChallengeRepository,
    ChallengeTestPolicy,
    ChallengeWindow,
    EvaluationEvidence,
    ParticipantReference,
    ParticipantRole,
    PromotionCriterion,
)
from afre.feature_store.models import AvailabilityEvidence
from afre.fusion import (
    ExternalFusionDefinition,
    ExternalFusionOutput,
    FusionEngine,
    FusionFamily,
    FusionKind,
)
from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.schema import DistributionFamily
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from examples.feature_store_demo import SOURCE
from examples.fusion_fixture import FusionFixture, build_fixture


@dataclass(frozen=True)
class ChallengeFixture:
    upstream: FusionFixture
    participants: tuple[ParticipantReference, ...]
    outputs: tuple[tuple[str, tuple[str, ...]], ...]


def build_challenge_fixture(
    repo: ChallengeRepository, reverse: bool = False
) -> ChallengeFixture:
    upstream = build_fixture(repo, reverse)
    engine, challenge = FusionEngine(repo), ChallengeEngine(repo)
    participants, produced = [], []
    samples = tuple(
        repo.get(ResearchSample, i)
        for i in (*upstream.train, *upstream.validation, *upstream.test)
    )
    for name, offset, role in (
        ("champion", 0.1, ParticipantRole.CHAMPION),
        ("better", 0.0, ParticipantRole.CHALLENGER),
        ("worse", 0.3, ParticipantRole.CHALLENGER),
    ):
        definition = ExternalFusionDefinition(
            name,
            SOURCE.provenance.system,
            "1",
            upstream.definitions[0].target,
            FusionKind.PROBABILISTIC,
            upstream.spec.unit,
            SOURCE,
            0,
        )
        raw = []
        for sample in reversed(samples) if reverse else samples:
            assert sample.origin is not None
            value = (
                5.0 / (100.0 + sample.timestamp_ns + int(sample.security.value) - 1) + offset
            )
            law = DistributionParameters(
                DistributionFamily.GAUSSIAN_LOCATION_SCALE, value, 0.05
            )
            at = sample.timestamp_ns
            raw.append(
                ExternalFusionOutput(
                    definition.fingerprint,
                    sample.fingerprint,
                    sample.origin,
                    value,
                    law,
                    AvailabilityEvidence(at, at, at, at),
                    "initial",
                )
            )
        engine.external(definition, tuple(raw))
        ref = engine.source(min(raw, key=lambda r: r.sample_id).fingerprint)
        spec = replace(
            upstream.spec,
            name=name,
            source_ids=(ref.fingerprint,),
            weights=((ref.fingerprint, 1.0),),
            kind=FusionKind.PROBABILISTIC,
            family=FusionFamily.FIXED_PROBABILITY_MIXTURE,
        )
        model = engine.fit(spec, 0, 0, 0)
        engine.choose_test(model.fingerprint, 0, "predeclared-independent-challenge-fixture")
        forecasts = tuple(
            engine.apply(
                model.fingerprint,
                r.sample_id,
                (engine.observe(ref.fingerprint, r.fingerprint).fingerprint,),
                r.origin.timestamp_ns,
            )
            for r in raw
        )
        # Boundary examples select a validation output at its earliest origin.
        # Content hashes cannot determine a forecast's temporal or TEST role.
        outputs = tuple(
            f.fingerprint
            for f in sorted(
                forecasts,
                key=lambda f: (
                    {Partition.VALIDATION: 0, Partition.TRAIN: 1, Partition.TEST: 2}[
                        f.partition
                    ],
                    f.origin.timestamp_ns,
                    f.security.fingerprint,
                    f.fingerprint,
                ),
            )
        )
        participant = challenge.participant(name, role, model.fingerprint)
        participants.append(participant)
        produced.append((participant.fingerprint, outputs))
    return ChallengeFixture(upstream, tuple(participants), tuple(sorted(produced)))


def program_for(
    fixture: ChallengeFixture,
    kinds: tuple[ChallengeMetric, ...] = (ChallengeMetric.MAE,),
    minimum: int = 2,
    start: int = 40,
    cutoff: int = 120,
    test: bool = False,
) -> tuple[ChallengeProgram, tuple[PromotionCriterion, ...]]:
    champion, *challengers = fixture.participants
    ref = champion.reference
    assert ref.dataset_id is not None and ref.fold_id is not None
    requests = tuple(ChallengeMetricRequest(k, minimum) for k in kinds)
    criteria = tuple(
        PromotionCriterion(
            k.value,
            r.fingerprint,
            ChallengeDirection.HIGHER
            if k
            in (
                ChallengeMetric.PEARSON,
                ChallengeMetric.SPEARMAN,
                ChallengeMetric.R_SQUARED,
                ChallengeMetric.SIGN_ACCURACY,
                ChallengeMetric.IC,
                ChallengeMetric.RANK_IC,
                ChallengeMetric.TOP_K_OVERLAP,
            )
            else ChallengeDirection.LOWER,
            0.0,
            minimum,
            0,
        )
        for k, r in zip(kinds, requests, strict=True)
    )
    program = ChallengeProgram(
        "known-challenge",
        champion.fingerprint,
        tuple(p.fingerprint for p in challengers),
        ref.target_id,
        ref.horizon_id,
        ref.unit,
        ref.dataset_id,
        ref.fold_id,
        ChallengeWindow(start, start + 1, cutoff),
        minimum,
        requests,
        tuple(c.fingerprint for c in criteria),
        (),
        ChallengeTestPolicy.SEALED_TEST if test else ChallengeTestPolicy.VALIDATION_ONLY,
        0,
    )
    return program, criteria


def evidence_for(
    repo: ChallengeRepository,
    fixture: ChallengeFixture,
    program: ChallengeProgram,
    test_evaluation_id: str | None = None,
    available_ns: int = 120,
) -> EvaluationEvidence:
    engine = ChallengeEngine(repo)
    shadows = []
    for participant, outputs in fixture.outputs:
        for identity in outputs:
            from afre.fusion.artifacts import FusedForecast

            source = repo.get(FusedForecast, identity)
            if program.window.contains(source.origin.timestamp_ns):
                shadows.append(
                    engine.shadow(
                        program.fingerprint, participant, identity, source.origin.timestamp_ns
                    ).fingerprint
                )
    samples = tuple(
        repo.get(ResearchSample, i)
        for i in (fixture.upstream.test if test_evaluation_id else fixture.upstream.validation)
    )
    truths = tuple(
        (s.fingerprint, s.target_id)
        for s in samples
        if s.target_id is not None and program.window.contains(s.timestamp_ns)
    )
    return EvaluationEvidence(
        program.fingerprint, tuple(shadows), truths, available_ns, test_evaluation_id
    )
