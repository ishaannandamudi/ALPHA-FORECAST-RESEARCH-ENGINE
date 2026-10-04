"""Canonical JSON with a closed data-only decoder."""

import json
import math
from dataclasses import fields
from enum import Enum
from typing import cast

from afre.schema import CONTRACTS, ENUMS, Artifact, ContractError, ensure_artifact, require
from afre.version import FOUNDATION_SCHEMA_VERSION

MAX_PAYLOAD_BYTES = 16 * 1024 * 1024
MAX_DEPTH = 64
JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]


def _wire(value: object, depth: int = 0) -> JSONValue:
    require(depth <= MAX_DEPTH, "artifact nesting too deep")
    if value is None or type(value) in (bool, int, str):
        return cast(JSONValue, value)
    if type(value) is float:
        assert isinstance(value, float)
        require(math.isfinite(value), "nonfinite number")
        return 0.0 if value == 0.0 else value
    if isinstance(value, Enum):
        require(ENUMS.get(type(value).__name__) is type(value), "unregistered enum")
        return {"$enum": type(value).__name__, "value": value.value}
    if type(value) is tuple:
        return [_wire(item, depth + 1) for item in value]
    artifact = ensure_artifact(value)
    return {
        "$type": type(artifact).__name__,
        "fields": {
            field.name: _wire(getattr(artifact, field.name), depth + 1)
            for field in fields(artifact)
        },
    }


def canonical_json(artifact: Artifact) -> str:
    ensure_artifact(artifact)
    payload = json.dumps(
        {"schema_version": FOUNDATION_SCHEMA_VERSION, "artifact": _wire(artifact)},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    require(len(payload.encode("utf-8")) <= MAX_PAYLOAD_BYTES, "artifact too large")
    return payload


def _unique_pairs(pairs: list[tuple[str, JSONValue]]) -> dict[str, JSONValue]:
    result: dict[str, JSONValue] = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractError(f"nonfinite JSON constant: {value}")


def _unwire(value: JSONValue, depth: int = 0) -> object:
    require(depth <= MAX_DEPTH, "artifact nesting too deep")
    if isinstance(value, list):
        return tuple(_unwire(item, depth + 1) for item in value)
    if isinstance(value, dict):
        if "$enum" in value:
            require(set(value) == {"$enum", "value"}, "invalid enum tag")
            tag = value["$enum"]
            require(isinstance(tag, str) and tag in ENUMS, "unknown enum")
            assert isinstance(tag, str)
            return ENUMS[tag](value["value"])
        require(set(value) == {"$type", "fields"}, "invalid artifact tag")
        name, raw = value["$type"], value["fields"]
        require(isinstance(name, str) and name in CONTRACTS, "unknown artifact class")
        require(isinstance(raw, dict), "invalid artifact fields")
        assert isinstance(name, str) and isinstance(raw, dict)
        cls = CONTRACTS[name]
        require(set(raw) == {field.name for field in fields(cls)}, "artifact fields mismatch")
        return cls(**{key: _unwire(item, depth + 1) for key, item in raw.items()})
    return value


def deserialize(payload: str) -> Artifact:
    try:
        require(
            type(payload) is str and len(payload.encode("utf-8")) <= MAX_PAYLOAD_BYTES,
            "invalid payload size/type",
        )
        parsed = json.loads(
            payload, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant
        )
        require(
            isinstance(parsed, dict) and set(parsed) == {"schema_version", "artifact"},
            "invalid envelope",
        )
        require(
            parsed["schema_version"] == FOUNDATION_SCHEMA_VERSION, "unknown contract schema"
        )
        artifact = ensure_artifact(_unwire(parsed["artifact"]))
        require(canonical_json(artifact) == payload, "noncanonical or altered payload")
        return artifact
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError) as error:
        raise ContractError(f"unsafe or invalid serialized artifact: {error}") from error
