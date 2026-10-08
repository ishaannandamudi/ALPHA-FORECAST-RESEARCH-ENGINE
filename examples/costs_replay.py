"""Fresh offline native construction across seeds/order, plus canonical restart digest."""

import hashlib
import socket
import sys
from pathlib import Path

from afre.costs import CostResearchRepository
from afre.serialization import canonical_json
from examples.costs_demo import run


def main() -> None:
    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("network forbidden in cost replay")

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
    report = run(path, reverse=sys.argv[2] == "reverse")
    assert len(report["steps"]) == 40  # type: ignore[arg-type]
    with CostResearchRepository(path) as repo, repo.read_snapshot(), repo.validation_cache():
        identities = tuple(
            row[0]
            for row in repo._connection.execute(
                "SELECT fingerprint FROM cost_artifacts ORDER BY fingerprint"
            )
        )
        payloads = tuple(canonical_json(repo.get_any(i)) for i in identities)
    print(hashlib.sha256("\n".join(payloads).encode()).hexdigest())


if __name__ == "__main__":
    main()
