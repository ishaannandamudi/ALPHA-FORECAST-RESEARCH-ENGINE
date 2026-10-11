"""Wrap exact frozen outputs under mandatory target protection before cache access."""

from typing import TYPE_CHECKING

from afre.challenger.artifacts import ShadowForecast
from afre.challenger.participants import ParticipantReference
from afre.challenger.programs import ChallengeProgram
from afre.challenger.schema import ChallengeTestPolicy, ShadowMode
from afre.health.probabilities import law_for
from afre.health.sources import observation_for
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import require

if TYPE_CHECKING:
    from afre.challenger.repository import ChallengeRepository


def shadow_for(
    repo: "ChallengeRepository",
    program: ChallengeProgram,
    participant_id: str,
    source_id: str,
    computed_ns: int,
) -> ShadowForecast:
    require(
        participant_id in (program.champion_id, *program.challenger_ids),
        "shadow participant fixed by program",
    )
    require(
        computed_ns >= program.declared_ns, "shadow cannot precede actual program declaration"
    )
    with repo.feature_only():
        participant = repo.resolve(ParticipantReference, participant_id)
        observation = observation_for(repo, participant.reference, source_id, computed_ns)
        require(
            observation.sample_id is not None
            and observation.security_id is not None
            and observation.partition is not None,
            "shadow exact native research sample",
        )
        assert observation.sample_id is not None and observation.security_id is not None
        assert observation.partition is not None
        require(
            observation.partition
            is (
                Partition.TEST
                if program.test_policy is ChallengeTestPolicy.SEALED_TEST
                else Partition.VALIDATION
            ),
            "shadow native partition matches explicit challenge TEST policy",
        )
        sample = repo.resolve(ResearchSample, observation.sample_id)
        require(
            sample.origin is not None and not sample.dropped,
            "shadow exact eligible admitted origin",
        )
        assert sample.origin is not None
        require(
            observation.available_ns <= sample.origin.availability_cutoff_ns
            and participant.reference.available_ns
            <= (
                sample.origin.availability_cutoff_ns
                if program.shadow_mode is ShadowMode.RECORDED_CAUSAL
                else computed_ns
            ),
            "shadow native source and artifact causal availability",
        )
        law = None
        if not source_id.startswith("afre.ort_"):
            law, _ = law_for(repo, source_id)
        return ShadowForecast(
            program.fingerprint,
            participant_id,
            source_id,
            observation.sample_id,
            observation.security_id,
            observation.valid_ns,
            participant.reference.target_id,
            participant.reference.horizon_id,
            observation.unit,
            dict(observation.values).get("prediction"),
            law.fingerprint if law else None,
            observation.partition,
            observation.available_ns,
            computed_ns,
            max(observation.available_ns, computed_ns),
            program.shadow_mode,
            observation.quality,
        )
