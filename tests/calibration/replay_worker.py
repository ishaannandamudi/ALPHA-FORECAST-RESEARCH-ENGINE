"""Offline child-process replay across hash seeds and insertion orders."""

import json
import socket
import sys
from pathlib import Path

from afre.calibration import CalibrationEngine, CalibrationMethod, CalibrationState
from afre.serialization import canonical_json
from examples.calibration_demo import (
    CalibrationDemoRepository,
    build_calibration_fixture,
    method_spec,
)


def deny(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in calibration replay")


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
    values: list[str] = []
    with CalibrationDemoRepository(path) as repo:
        fixture = build_calibration_fixture(repo, reverse=sys.argv[2] == "reverse")
        engine = CalibrationEngine(repo)
        for method in (
            CalibrationMethod.ISOTONIC_PROBABILITY,
            CalibrationMethod.QUANTILE_OFFSET,
            CalibrationMethod.ROLLING_CONFORMAL,
        ):
            requests = (
                tuple(reversed(fixture.requests))
                if sys.argv[2] == "reverse"
                else fixture.requests
            )
            run = engine.fit(method_spec(fixture, method), requests, 55, 55, 55)
            fs = engine.apply_batch(
                run.state_id, tuple(p.fingerprint for p in fixture.deployment_raw)
            )
            evaluation = engine.evaluate(tuple(f.fingerprint for f in fs), 75, 75)
            comparison = engine.compare(evaluation.raw_evaluation_id, evaluation.fingerprint)
            values.extend(
                canonical_json(v)
                for v in (repo.get(CalibrationState, run.state_id), *fs, evaluation, comparison)
            )
        identities = tuple(
            v.fingerprint
            for v in (repo.get(CalibrationState, run.state_id), *fs, evaluation, comparison)
        )
        frozen = tuple(canonical_json(repo.get_any(i)) for i in identities)
    with CalibrationDemoRepository(path) as restarted:
        assert tuple(canonical_json(restarted.get_any(i)) for i in identities) == frozen
    print(json.dumps(values, separators=(",", ":")))


if __name__ == "__main__":
    main()
