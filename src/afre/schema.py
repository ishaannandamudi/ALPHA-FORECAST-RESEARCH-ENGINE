"""Closed, immutable contract schema and strict runtime validation."""

import math
import types
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import ClassVar, TypeVar, get_args, get_origin

from afre.version import FOUNDATION_SCHEMA_VERSION


class ContractError(ValueError):
    """An artifact fails its structural or research invariants."""


CONTRACTS: dict[str, type["Artifact"]] = {}
ENUMS: dict[str, type[Enum]] = {}
A = TypeVar("A", bound="Artifact")
E = TypeVar("E", bound=Enum)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def enum(cls: type[E]) -> type[E]:
    require(cls.__name__ not in ENUMS, "duplicate enum registration")
    ENUMS[cls.__name__] = cls
    return cls


def contract(domain: str) -> Callable[[type[A]], type[A]]:
    def register(cls: type[A]) -> type[A]:
        require(cls.__name__ not in CONTRACTS, "duplicate contract registration")
        cls.domain = domain
        CONTRACTS[cls.__name__] = cls
        return cls

    return register


def matches(value: object, annotation: object) -> bool:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is types.UnionType:
        return any(matches(value, arg) for arg in args)
    if origin is tuple:
        if type(value) is not tuple:
            return False
        if len(args) == 2 and args[1] is Ellipsis:
            return all(matches(item, args[0]) for item in value)
        return len(value) == len(args) and all(
            matches(item, expected) for item, expected in zip(value, args, strict=True)
        )
    return isinstance(annotation, type) and type(value) is annotation


@dataclass(frozen=True, slots=True)
class Artifact:
    domain: ClassVar[str]
    schema_version: ClassVar[str] = FOUNDATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in fields(self):
            value = getattr(self, field.name)
            require(matches(value, field.type), f"{field.name}: wrong contract type")
            self._validate_scalar(value)
            if field.name.endswith("_ns") and value is not None:
                require(0 <= value <= 2**63 - 1, f"{field.name}: invalid UTC nanoseconds")
        self._normalize()
        self._validate()

    @staticmethod
    def _validate_scalar(value: object) -> None:
        if isinstance(value, str):
            require(bool(value.strip()), "empty text")
            require(not any(ord(c) < 32 for c in value), "control character in text")
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), "invalid Unicode text")
        elif isinstance(value, float):
            require(math.isfinite(value), "nonfinite number")
        elif isinstance(value, tuple):
            for item in value:
                Artifact._validate_scalar(item)

    def _normalize(self) -> None:
        pass

    def _validate(self) -> None:
        pass

    def ordered(self, name: str, key: str) -> None:
        values = getattr(self, name)
        ordered = tuple(sorted(values, key=lambda x: getattr(x, key)))
        identities = tuple(getattr(x, key) for x in ordered)
        require(len(set(identities)) == len(identities), f"duplicate {name}")
        object.__setattr__(self, name, ordered)

    @property
    def fingerprint(self) -> str:
        from afre.hashing import fingerprint

        return fingerprint(self)


def ensure_artifact(value: object) -> Artifact:
    require(isinstance(value, Artifact) and is_dataclass(value), "not an artifact")
    assert isinstance(value, Artifact)
    require(CONTRACTS.get(type(value).__name__) is type(value), "unregistered artifact")
    return value
