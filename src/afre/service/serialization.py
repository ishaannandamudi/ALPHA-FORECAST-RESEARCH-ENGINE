"""Canonical UTC-nanosecond, finite-float, closed JSON public boundary."""

from afre.schema import Artifact, require
from afre.serialization import canonical_json as native_json
from afre.serialization import deserialize as native_deserialize


def canonical_json(value: Artifact) -> str:
    require(
        value.domain.startswith("svc_"), "public service serialization requires service root"
    )
    return native_json(value)


def deserialize(payload: str) -> Artifact:
    value = native_deserialize(payload)
    require(
        value.domain.startswith("svc_"), "public service deserialization requires service root"
    )
    return value
