"""Fresh AFRE-16 construction against frozen earlier phases, with network disabled."""

import hashlib
import socket
import sys
from pathlib import Path

from afre.orthogonalization import OrthogonalizationEngine, OrthogonalizationRepository
from afre.research_datasets.schema import Partition
from afre.serialization import canonical_json
from afre.target_engine.definitions import TargetDefinition
from examples.orthogonalization_fixture import build_rows


def denied(*args: object, **kwargs: object) -> None:
    raise AssertionError("network forbidden in orthogonalization replay")


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
    with OrthogonalizationRepository(path) as r:
        e = OrthogonalizationEngine(r)
        spec, rows = build_rows(
            r, sys.argv[3], r.get(TargetDefinition, sys.argv[4]), 40, reverse=reverse
        )
        train = tuple(x.fingerprint for x in rows if x.partition is Partition.TRAIN)
        model = e.fit(spec, tuple(reversed(train)) if reverse else train, 40)
        values = tuple(
            e.residual(model.fingerprint, x.fingerprint, x.origin.timestamp_ns)
            for x in (tuple(reversed(rows)) if reverse else rows)
            if x.partition is not Partition.TRAIN
        )
        pair = e.fit_target_models(model.fingerprint, 40)
        for partition in (Partition.VALIDATION, Partition.TEST):
            samples = {x.sample_id for x in rows if x.partition is partition}
            ids = tuple(v.fingerprint for v in values if v.sample_id in samples)
            evaluation = e.evaluate(
                ids,
                100,
                100,
                pair.fingerprint,
                True,
                "seed-TEST" if partition is Partition.TEST else None,
            )
            e.audit_lineage(evaluation.fingerprint)
        identities = tuple(
            x[0]
            for x in r._connection.execute(
                "SELECT fingerprint FROM ort_artifacts ORDER BY fingerprint"
            )
        )
        before = tuple(canonical_json(r.get_any(i)) for i in identities)
    with OrthogonalizationRepository(path) as r:
        assert tuple(canonical_json(r.get_any(i)) for i in identities) == before
    print(hashlib.sha256("\n".join(before).encode()).hexdigest())


if __name__ == "__main__":
    main()
