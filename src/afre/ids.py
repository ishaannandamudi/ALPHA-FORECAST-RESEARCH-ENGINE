"""Stable security identities and domain-aware artifact references."""

import re
from dataclasses import dataclass

from afre.schema import Artifact, contract, require


@contract("instrument")
@dataclass(frozen=True, slots=True)
class InstrumentId(Artifact):
    namespace: str
    value: str

    def _validate(self) -> None:
        for part in (self.namespace, self.value):
            require(
                bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", part)),
                "invalid stable security identity",
            )


def validate_digest(value: str) -> None:
    require(bool(re.fullmatch(r"[0-9a-f]{64}", value)), "invalid SHA-256 digest")


def validate_fingerprint(value: str, domain: str | None = None) -> None:
    require(
        bool(re.fullmatch(r"afre\.[a-z_]+:1\.0:[0-9a-f]{64}", value)),
        "invalid artifact fingerprint",
    )
    if domain is not None:
        require(value.startswith(f"afre.{domain}:1.0:"), "wrong artifact namespace")
