"""Offline fresh AFRE-17 construction over frozen AFRE-0 through16 artifacts."""

import hashlib
import socket
import sys
from dataclasses import replace
from pathlib import Path

from afre.invariance import (
    EnvironmentSet,
    InvarianceEngine,
    InvarianceRepository,
    StabilityAnalysisSpec,
)
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json, deserialize


def main() -> None:
    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("network forbidden in invariance replay")

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
    envs = deserialize(Path(sys.argv[2]).read_text())
    spec = deserialize(Path(sys.argv[3]).read_text())
    assert isinstance(envs, EnvironmentSet) and isinstance(spec, StabilityAnalysisSpec)
    reverse = sys.argv[4] == "reverse"
    with InvarianceRepository(path) as repo:
        e = InvarianceEngine(repo)
        for d in reversed(envs.definitions) if reverse else envs.definitions:
            e._publish((d.target, d))
        e.declare(envs)
        s = e.register(
            replace(
                spec,
                sample_ids=tuple(reversed(spec.sample_ids)) if reverse else spec.sample_ids,
                forecast_ids=tuple(reversed(spec.forecast_ids))
                if reverse
                else spec.forecast_ids,
                metrics=tuple(reversed(spec.metrics)) if reverse else spec.metrics,
            )
        )
        members = tuple(
            e.bind(
                d.fingerprint, i, constructed_ns=repo.get(ResearchSample, i).timestamp_ns
            ).fingerprint
            for d in (reversed(envs.definitions) if reverse else envs.definitions)
            for i in (reversed(s.sample_ids) if reverse else s.sample_ids)
        )
        results = e.evaluate(
            s.fingerprint, tuple(reversed(members)) if reverse else members, 100, 100
        )
        e.compare(results[0].fingerprint, results[len(spec.metrics)].fingerprint, 100)
        e.audit(results[0].fingerprint)
        identities = tuple(
            row[0]
            for row in repo._connection.execute(
                "SELECT fingerprint FROM inv_artifacts ORDER BY fingerprint"
            )
        )
        before = tuple(canonical_json(repo.get_any(i)) for i in identities)
    with InvarianceRepository(path) as repo:
        assert before == tuple(canonical_json(repo.get_any(i)) for i in identities)
    print(hashlib.sha256("\n".join(before).encode()).hexdigest())


if __name__ == "__main__":
    main()
