"""One global intersection, exact truth vintages and pre-target TEST gates."""

from typing import TYPE_CHECKING

from afre.challenger.artifacts import CommonMatchedEvidence, EvaluationEvidence, ShadowForecast
from afre.challenger.participants import ParticipantReference
from afre.challenger.programs import ChallengeProgram
from afre.challenger.schema import ChallengeStatus as S
from afre.challenger.schema import ChallengeTestPolicy, ShadowMode
from afre.fusion.artifacts import FrozenFusionTestChoice, FusedForecast
from afre.invariance.artifacts import EnvironmentMembership
from afre.invariance.schema import EnvironmentState
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.challenger.repository import ChallengeRepository


def common_for(
    repo: "ChallengeRepository", program: ChallengeProgram, evidence: EvaluationEvidence
) -> CommonMatchedEvidence:
    require(
        evidence.program_id == program.fingerprint
        and evidence.available_ns >= program.window.cutoff_ns,
        "exact program/evaluation clock",
    )
    participants = (program.champion_id, *program.challenger_ids)
    declared = tuple(repo.resolve(ParticipantReference, i) for i in participants)
    incompatible = any(
        (
            r.reference.target_id,
            r.reference.horizon_id,
            r.reference.unit,
            r.dataset_id,
            r.fold_id,
        )
        != (
            program.target_id,
            program.horizon_id,
            program.unit,
            program.dataset_id,
            program.fold_id,
        )
        for r in declared
    )
    shadows = tuple(repo.resolve(ShadowForecast, i) for i in evidence.shadow_ids)
    require(
        all(
            s.program_id == program.fingerprint
            and s.participant_id in participants
            and s.available_ns <= evidence.available_ns
            for s in shadows
        ),
        "evaluation exact shadow program/participant/availability",
    )
    require(
        len({(s.participant_id, s.sample_id) for s in shadows}) == len(shadows),
        "one explicit shadow revision per participant/sample",
    )
    by_key = {(s.participant_id, s.sample_id): s for s in shadows}
    assignments: list[tuple[str, str]] = []
    chosen: list[str] = []
    exclusions: list[tuple[str, str]] = []
    memberships = tuple(repo.resolve(EnvironmentMembership, i) for i in program.membership_ids)
    require(
        all(
            m.environment_id == program.environment_id
            and m.available_ns <= evidence.available_ns
            for m in memberships
        ),
        "exact shared cohort and construction availability",
    )
    require(
        len({m.sample_id for m in memberships}) == len(memberships),
        "one frozen cohort membership per sample",
    )
    incompatible = incompatible or any(m.soft for m in memberships)
    included = {m.sample_id for m in memberships if m.state is EnvironmentState.INCLUDED}
    seal = None
    if program.test_policy is ChallengeTestPolicy.SEALED_TEST:
        require(evidence.test_evaluation_id is not None, "sealed TEST requires native seal")
        assert evidence.test_evaluation_id is not None
        seal = repo.resolve(TestEvaluation, evidence.test_evaluation_id)
        require(
            seal.fold_id == program.fold_id and seal.evaluated_ns == program.window.cutoff_ns,
            "exact native TEST fold/cutoff",
        )
    else:
        require(evidence.test_evaluation_id is None, "validation cannot consume TEST seal")
    for sample_id, truth_id in evidence.truth_assignments:
        rows = tuple(by_key.get((p, sample_id)) for p in participants)
        reason = ""
        if incompatible:
            reason = "participant-target-horizon-unit-fold-or-soft-cohort-incomparable"
        elif any(s is None for s in rows):
            reason = "missing-participant-shadow"
        else:
            exact = tuple(s for s in rows if s is not None)
            require(
                len({s.origin_ns for s in exact}) == 1
                and len({s.security_id for s in exact}) == 1,
                "same sample exact origin/security",
            )
            if not program.window.contains(exact[0].origin_ns):
                reason = "outside-frozen-window"
            elif program.environment_id is not None and sample_id not in included:
                reason = "outside-frozen-cohort"
            elif program.shadow_mode is ShadowMode.RECORDED_CAUSAL and any(
                s.available_ns > s.origin_ns for s in exact
            ):
                reason = "late-shadow"
            else:
                expected = Partition.TEST if seal else Partition.VALIDATION
                require(
                    all(s.partition is expected for s in exact),
                    "challenge partition policy before truth access",
                )
                if seal:
                    require(sample_id in seal.sample_ids, "native TEST exact sample seal")
                    for s in exact:
                        source = repo.get_any(s.source_id)
                        if isinstance(source, FusedForecast):
                            require(
                                any(
                                    (
                                        choice := repo.resolve(FrozenFusionTestChoice, i[0])
                                    ).artifact_id
                                    == source.artifact_id
                                    and choice.declared_ns <= program.window.start_ns
                                    for i in repo._connection.execute(
                                        "SELECT fingerprint FROM fus_artifacts WHERE "
                                        "type_name='FrozenFusionTestChoice'"
                                    )
                                ),
                                "retain native frozen fusion TEST choice",
                            )
                sample = repo.resolve(ResearchSample, sample_id)
                truth = repo.resolve(TargetVintage, truth_id)
                require(
                    truth.origin == sample.origin
                    and truth.definition.fingerprint == program.target_id,
                    "exact explicit truth vintage/origin/target",
                )
                if (
                    not target_known_by_cutoff(truth, program.window.cutoff_ns)
                    or truth.value is None
                ):
                    reason = "truth-not-known-by-frozen-cutoff"
                else:
                    assignments.append((sample_id, truth_id))
                    chosen.extend(s.fingerprint for s in exact)
        if reason:
            exclusions.append((sample_id, reason))
    assigned = {s for s, _ in evidence.truth_assignments}
    exclusions.extend(
        (s.fingerprint, "no-explicit-truth-assignment")
        for s in shadows
        if s.sample_id not in assigned
    )
    status = (
        S.INCOMPARABLE
        if incompatible
        else S.AVAILABLE
        if (len(assignments) >= program.minimum_count)
        else S.INSUFFICIENT_DATA
    )
    return CommonMatchedEvidence(
        program.fingerprint,
        evidence.fingerprint,
        tuple(assignments),
        tuple(chosen),
        tuple(exclusions),
        status,
        "exact-global-common-intersection" if status is S.AVAILABLE else status.value,
        program.window.cutoff_ns,
        evidence.available_ns,
    )
