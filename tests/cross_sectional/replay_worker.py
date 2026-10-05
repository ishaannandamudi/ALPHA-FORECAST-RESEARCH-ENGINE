"""Fresh interpreter replay, explicitly blocking all sockets and DNS."""

import json
import socket
import sys
from pathlib import Path

from afre.cross_sectional import CrossSectionEngine, CrossSectionRepository
from afre.serialization import canonical_json
from examples.cross_sectional_demo import cross_fixture
from tests.cross_sectional.conftest import Case
from tests.cross_sectional.test_evaluation import second_ranking


def denied(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in cross-sectional replay")


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
    path = Path(sys.argv[1])
    with CrossSectionRepository(path) as repo:
        f = cross_fixture(repo, reverse=sys.argv[2] == "reverse")
        engine = CrossSectionEngine(repo)
        evaluation = engine.evaluate(f.ranking.fingerprint, f.targets, 100, 100)
        later, targets = second_ranking(Case(path, repo, f))
        later_eval = engine.evaluate(later.fingerprint, targets, 100, 100)
        series = engine.aggregate_ic((evaluation.fingerprint, later_eval.fingerprint))
        stability = engine.stability(f.ranking.fingerprint, later.fingerprint)
        audit = engine.audit_lineage(evaluation.fingerprint)
        values = (f.spec, f.ranking, evaluation, later, later_eval, series, stability, audit)
        payloads = [canonical_json(v) for v in values]
    with CrossSectionRepository(path) as repo:
        assert [canonical_json(repo.get_any(v.fingerprint)) for v in values] == payloads
        repo.audit()
    print(json.dumps(payloads))


if __name__ == "__main__":
    main()
