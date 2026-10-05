"""Fresh-process event/reaction/request reversal, socket blocking and restart replay."""

import json
import socket
import sys
from dataclasses import replace
from pathlib import Path

from afre.cross_sectional import CrossSectionEngine
from afre.event_conditioned import (
    EventEngine,
    EventModelFamily,
    EventOverlapPolicy,
    EventRelation,
    EventRepository,
)
from afre.event_conditioned.artifacts import (
    EventConditionedForecast,
    EventConditionedObservation,
)
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from examples.cross_sectional_demo import external
from examples.event_conditioned_demo import build_fixture, event


def denied(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in event replay")


def main() -> None:
    for name in (
        "socket",
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
        "socketpair",
    ):
        setattr(socket, name, denied)
    path, reverse = Path(sys.argv[1]), sys.argv[2] == "reverse"
    with EventRepository(path) as repo:
        f = build_fixture(repo, reverse)
        engine = EventEngine(repo)
        ids = tuple(reversed(f.forecast_ids)) if reverse else f.forecast_ids
        result = engine.evaluate(ids, 100, 100)
        rank = engine.rank(
            f.upstream.spec,
            ids,
            tuple(reversed(f.upstream.group_refs)) if reverse else f.upstream.group_refs,
        )
        evaluation = engine.evaluate_rank(rank.fingerprint, 100, 100)
        p = repo.get(EventConditionedForecast, f.forecast_ids[0])
        o = repo.get(EventConditionedObservation, p.observation_id)
        sample = repo.get(ResearchSample, o.sample_id)
        events = [event(sample, name, at=59) for name in ("overlap-a", "overlap-b")]
        reactions = [
            external(sample.security, 60, 0.2),
            external(repo.get(EventConditionedForecast, f.forecast_ids[-1]).security, 60, 0.3),
        ]
        if reverse:
            events.reverse()
            reactions.reverse()
        event_ids = tuple(engine.publish_event(e) for e in events)
        for s in reactions:
            CrossSectionEngine(repo).publish_external(s)
        spec = replace(
            f.spec,
            family=EventModelFamily.EVENT_FEATURE_LINEAR,
            window=replace(
                f.spec.window, relation=EventRelation.POST_EVENT, post_maximum_age_ns=2
            ),
            reaction_specs=(f.upstream.spec.score,),
            overlap=EventOverlapPolicy.ALL_EVENTS_SEPARATE,
        )
        observations = engine.observe(
            spec, o.sample_id, event_ids, tuple(s.fingerprint for s in reactions)
        )
        audit = engine.audit_lineage(evaluation.fingerprint)
        values = (
            f.spec,
            f.model,
            *(repo.get(EventConditionedForecast, i) for i in f.forecast_ids),
            result,
            rank,
            evaluation,
            *observations,
            audit,
        )
        payloads = [canonical_json(v) for v in values]
    with EventRepository(path) as repo:
        assert [canonical_json(repo.get_any(v.fingerprint)) for v in values] == payloads
        repo.audit()
    print(json.dumps(payloads))


if __name__ == "__main__":
    main()
