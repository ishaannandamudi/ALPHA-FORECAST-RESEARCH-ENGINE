"""Fresh process, blocked networking, reordered taxonomies/snapshots/requests and restart."""

import json
import socket
import sys
from pathlib import Path

from afre.regime_conditioned import RegimeEngine, RegimeRepository, RegimeScope
from afre.serialization import canonical_json
from examples.regime_conditioned_demo import build_fixture, taxonomy


def denied(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in regime replay")


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
    with RegimeRepository(path) as repo:
        engine = RegimeEngine(repo)
        taxonomies = (taxonomy(), taxonomy(True))
        for t in reversed(taxonomies) if reverse else taxonomies:
            engine.publish_taxonomy(t)
        hard = build_fixture(repo, reverse)
        soft = build_fixture(repo, reverse, upstream=hard.upstream, soft=True)
        global_f = build_fixture(
            repo, reverse, upstream=hard.upstream, scope=RegimeScope.GLOBAL
        )
        ids = tuple(reversed(hard.forecast_ids)) if reverse else hard.forecast_ids
        evaluation = engine.evaluate(ids, 100, 100)
        soft_eval = engine.evaluate(
            tuple(reversed(soft.forecast_ids)) if reverse else soft.forecast_ids, 100, 100
        )
        test = engine.evaluate(hard.test_ids, 100, 100, "regime-replay-TEST")
        drift = engine.drift(evaluation.fingerprint, test.fingerprint, 100)
        ranking = engine.rank(
            hard.upstream.spec,
            ids,
            tuple(reversed(hard.upstream.group_refs)) if reverse else hard.upstream.group_refs,
        )
        rank_eval = engine.evaluate_rank(ranking.fingerprint, 100, 100)
        audit = engine.audit_lineage(rank_eval.fingerprint)
        values = (
            hard.spec,
            hard.model,
            soft.model,
            global_f.model,
            *(
                repo.get_any(i)
                for i in (*hard.forecast_ids, *soft.forecast_ids, *global_f.forecast_ids)
            ),
            evaluation,
            soft_eval,
            test,
            drift,
            ranking,
            rank_eval,
            audit,
        )
        payloads = [canonical_json(v) for v in values]
    with RegimeRepository(path) as repo:
        assert [canonical_json(repo.get_any(v.fingerprint)) for v in values] == payloads
        repo.audit()
    print(json.dumps(payloads))


if __name__ == "__main__":
    main()
