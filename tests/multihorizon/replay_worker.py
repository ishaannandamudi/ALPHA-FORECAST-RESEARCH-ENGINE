"""Fresh interpreter worker with explicit socket/DNS blocking."""

import json
import socket
import sys
from pathlib import Path

from afre.multihorizon import MultiHorizonEngine, MultiHorizonRepository
from afre.serialization import canonical_json
from examples.multihorizon_demo import backbone_spec, build_fixture


def denied(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in multi-horizon replay")


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
    with MultiHorizonRepository(Path(sys.argv[1])) as repo:
        fixture = build_fixture(repo, reverse=sys.argv[2] == "reverse")
        engine = MultiHorizonEngine(repo)
        shared = engine.fit(backbone_spec(fixture), 55, 55, 55)
        covariance = engine.fit_dependence(fixture.run.fingerprint, 40, 55)
        evaluation = engine.evaluate(tuple(b.fingerprint for b in fixture.bundles), 75, 75)
        audit = engine.lineage_audit(fixture.bundles[0].fingerprint)
        values = (
            fixture.spec,
            fixture.run,
            shared,
            covariance,
            evaluation,
            audit,
            *fixture.bundles,
        )
        print(json.dumps([canonical_json(v) for v in values]))


if __name__ == "__main__":
    main()
