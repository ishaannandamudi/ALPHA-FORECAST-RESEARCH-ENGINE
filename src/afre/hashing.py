"""Domain-separated SHA-256 identities, independent of Python object hashes."""

import hashlib

from afre.schema import Artifact, ensure_artifact
from afre.serialization import canonical_json
from afre.version import FOUNDATION_SCHEMA_VERSION


def bytes_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def fingerprint(artifact: Artifact) -> str:
    ensure_artifact(artifact)
    domain = artifact.domain
    prefix = f"AFRE\x00{FOUNDATION_SCHEMA_VERSION}\x00{domain}\x00".encode()
    digest = bytes_digest(prefix + canonical_json(artifact).encode("utf-8"))
    return f"afre.{domain}:{FOUNDATION_SCHEMA_VERSION}:{digest}"
