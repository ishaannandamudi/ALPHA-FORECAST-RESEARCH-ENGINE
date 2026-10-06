"""Fresh fully offline seed/order/restart semantic byte replay."""

import hashlib
import socket
import sys
from pathlib import Path

from afre.serialization import canonical_json
from afre.uncertainty import UncertaintyEngine, UncertaintyEvaluationSpec, UncertaintyRepository
from examples.uncertainty_fixture import build_fixture


def denied(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in uncertainty replay")


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
    reverse = sys.argv[2] == "reverse"
    with UncertaintyRepository(path) as repo:
        fixture = build_fixture(repo, reverse)
        engine = UncertaintyEngine(repo)
        sources = tuple(reversed(fixture.decompositions)) if reverse else fixture.decompositions
        for _, ids in sources:
            engine.evaluate(
                tuple(reversed(ids)) if reverse else ids,
                UncertaintyEvaluationSpec(bucket_count=2),
                100,
                100,
            )
        engine.evaluate(
            fixture.test_ids, UncertaintyEvaluationSpec(bucket_count=2), 100, 100, "replay-test"
        )
        identities = tuple(
            r[0]
            for r in repo._connection.execute(
                "SELECT fingerprint FROM unc_artifacts ORDER BY fingerprint"
            )
        )
        before = tuple(canonical_json(repo.get_any(i)) for i in identities)
    with UncertaintyRepository(path) as repo:
        assert tuple(canonical_json(repo.get_any(i)) for i in identities) == before
    print(hashlib.sha256("\n".join(before).encode()).hexdigest())


if __name__ == "__main__":
    main()
