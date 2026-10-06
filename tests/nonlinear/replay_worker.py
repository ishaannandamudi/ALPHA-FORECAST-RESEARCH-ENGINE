"""Fresh network-blocked process verifies all nonlinear semantic bytes after restart."""

import hashlib
import socket
import sys
from pathlib import Path

from afre.nonlinear import NonlinearRepository
from afre.serialization import canonical_json
from examples.nonlinear_demo import build_fixture


def deny(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in nonlinear replay")


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
    with NonlinearRepository(path) as repo:
        fixture = build_fixture(repo, reverse=sys.argv[2] == "reverse")
        from afre.nonlinear import NonlinearEngine

        engine = NonlinearEngine(repo)
        for ids in (
            reversed(fixture.forecast_ids) if sys.argv[2] == "reverse" else fixture.forecast_ids
        ):
            engine.evaluate(tuple(reversed(ids)) if sys.argv[2] == "reverse" else ids, 100, 100)
        identities = tuple(
            r[0]
            for r in repo._connection.execute(
                "SELECT fingerprint FROM nl_artifacts ORDER BY fingerprint"
            )
        )
        before = tuple(canonical_json(repo.get_any(i)) for i in identities)
    with NonlinearRepository(path) as repo:
        assert tuple(canonical_json(repo.get_any(i)) for i in identities) == before
    print(hashlib.sha256("\n".join(before).encode()).hexdigest())


if __name__ == "__main__":
    main()
