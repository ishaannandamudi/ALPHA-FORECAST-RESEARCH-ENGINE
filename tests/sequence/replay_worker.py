"""Fresh network-blocked process verifies all sequence semantic bytes after restart."""

import hashlib
import socket
import sys
from pathlib import Path

from afre.sequence import SequenceRepository
from afre.serialization import canonical_json
from examples.sequence_demo import build_fixture


def deny(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in sequence replay")


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
        setattr(socket, name, deny)
    path = Path(sys.argv[1])
    with SequenceRepository(path) as repo:
        fixture = build_fixture(repo, reverse=sys.argv[2] == "reverse")
        from afre.sequence import SequenceEngine

        engine = SequenceEngine(repo)
        for ids in (
            reversed(fixture.forecasts) if sys.argv[2] == "reverse" else fixture.forecasts
        ):
            engine.evaluate(tuple(reversed(ids)) if sys.argv[2] == "reverse" else ids, 100, 100)
        identities = tuple(
            r[0]
            for r in repo._connection.execute(
                "SELECT fingerprint FROM sq_artifacts ORDER BY fingerprint"
            )
        )
        before = tuple(canonical_json(repo.get_any(i)) for i in identities)
    with SequenceRepository(path) as repo:
        assert tuple(canonical_json(repo.get_any(i)) for i in identities) == before
    print(hashlib.sha256("\n".join(before).encode()).hexdigest())


if __name__ == "__main__":
    main()
