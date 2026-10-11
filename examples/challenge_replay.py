"""Fresh-process exact canonical challenge replay with every caller ordering reversed."""

import shutil
import sys
from dataclasses import replace
from pathlib import Path

from afre.challenger import (
    ChallengeEngine,
    ChallengeMetric,
    ChallengeRepository,
    ParticipantReference,
)
from afre.fusion import FusedForecast
from afre.serialization import canonical_json
from examples.challenger_fixture import ChallengeFixture, evidence_for, program_for
from examples.fusion_fixture import build_fixture


def replay(template: Path, destination: Path, reverse: bool) -> str:
    shutil.copyfile(template, destination)
    with ChallengeRepository(destination) as repo:
        participants = tuple(
            repo.get(ParticipantReference, r[0])
            for r in repo._connection.execute(
                "SELECT fingerprint FROM ch_artifacts WHERE type_name='ParticipantReference'"
            )
        )
        participants = tuple(
            sorted(participants, key=lambda p: {"champion": 0, "better": 1, "worse": 2}[p.name])
        )
        outputs = tuple(
            (
                p.fingerprint,
                tuple(
                    r[0]
                    for r in repo._connection.execute(
                        "SELECT fingerprint FROM fus_artifacts WHERE type_name='FusedForecast'"
                    )
                    if repo.get(FusedForecast, r[0]).artifact_id == p.reference.producer_id
                ),
            )
            for p in participants
        )
        fixture = ChallengeFixture(build_fixture(repo, reverse), participants, outputs)
        program, rules = program_for(
            fixture, (ChallengeMetric.MAE, ChallengeMetric.MSE, ChallengeMetric.CRPS)
        )
        if reverse:
            program = replace(
                program,
                challenger_ids=tuple(reversed(program.challenger_ids)),
                requests=tuple(reversed(program.requests)),
                promotion_criterion_ids=tuple(reversed(program.promotion_criterion_ids)),
            )
            rules = tuple(reversed(rules))
            fixture = replace(
                fixture,
                outputs=tuple(
                    (p, tuple(reversed(ids))) for p, ids in reversed(fixture.outputs)
                ),
            )
        engine = ChallengeEngine(repo)
        engine.declare(program, rules)
        evidence = evidence_for(repo, fixture, program)
        if reverse:
            evidence = replace(
                evidence,
                shadow_ids=tuple(reversed(evidence.shadow_ids)),
                truth_assignments=tuple(reversed(evidence.truth_assignments)),
            )
        engine.evidence(evidence)
        run = engine.evaluate(evidence.fingerprint)
        values = (
            program,
            *rules,
            evidence,
            run,
            *(
                repo.get_any(i)
                for i in (
                    run.common_id,
                    *run.metric_ids,
                    *run.comparison_ids,
                    *run.promotion_ids,
                )
            ),
        )
        return "\n".join(canonical_json(v) for v in sorted(values, key=lambda v: v.fingerprint))


if __name__ == "__main__":
    print(replay(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3] == "1"))
