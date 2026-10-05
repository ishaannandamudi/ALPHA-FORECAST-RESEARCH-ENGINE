"""Fresh offline seed/reversal/restart replay of expert, gate and evaluation bytes."""

import hashlib
import json
import socket
import sys
from pathlib import Path

from afre.mixture import MixtureEngine, MixtureRepository
from afre.serialization import canonical_json
from examples.mixture_demo import build_fixture


def denied(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in mixture replay")


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
    with MixtureRepository(path) as repo:
        fixture = build_fixture(repo, reverse)
        engine = MixtureEngine(repo)
        ids = tuple(reversed(fixture.forecast_ids)) if reverse else fixture.forecast_ids
        evaluation = engine.evaluate(ids, 100, 100)
        test = engine.evaluate(
            tuple(reversed(fixture.test_ids)) if reverse else fixture.test_ids,
            100,
            100,
            "mixture-replay-TEST",
        )
        diagnostic = engine.diagnostics(evaluation.fingerprint)
        drift = engine.drift(
            diagnostic.fingerprint, engine.diagnostics(test.fingerprint).fingerprint, 100
        )
        upstream = fixture.upstream.upstream
        rank = engine.rank(
            upstream.spec,
            ids,
            tuple(reversed(upstream.group_refs)) if reverse else upstream.group_refs,
        )
        rank_eval = engine.evaluate_rank(rank.fingerprint, 100, 100)
        audit = engine.audit_lineage(rank_eval.fingerprint)
        values = (
            fixture.fixed,
            fixture.learned_spec,
            fixture.learned,
            *(
                repo.get_any(i)
                for i in sorted(
                    (*fixture.forecast_ids, *fixture.learned_ids, *fixture.probability_ids)
                )
            ),
            evaluation,
            test,
            diagnostic,
            drift,
            rank,
            rank_eval,
            audit,
        )
        payloads = [canonical_json(v) for v in values]
    with MixtureRepository(path) as reader:
        assert [canonical_json(reader.get_any(v.fingerprint)) for v in values] == payloads
        reader.audit()
    print(hashlib.sha256(json.dumps(payloads).encode()).hexdigest())


if __name__ == "__main__":
    main()
