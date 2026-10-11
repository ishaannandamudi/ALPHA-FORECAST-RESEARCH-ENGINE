"""Exact public schema/capability catalog independent of SQLite layout."""

from dataclasses import dataclass

from afre.schema import Artifact, contract, require

CAPABILITIES = tuple(
    sorted(
        (
            "POINT",
            "PROBABILISTIC_GAUSSIAN",
            "PROBABILISTIC_EMPIRICAL",
            "PROBABILISTIC_MIXTURE",
            "QUANTILE_ONLY",
            "CALIBRATION",
            "MULTI_HORIZON",
            "RANKING",
            "EVENT_CONTEXT",
            "REGIME_CONTEXT",
            "UNCERTAINTY",
            "ORTHOGONAL_CONTEXT",
            "FUSION",
            "HEALTH",
            "CHALLENGE_METADATA",
        )
    )
)


@contract("svc_versions")
@dataclass(frozen=True, slots=True)
class VersionInfo(Artifact):
    engine: str
    api: str
    snapshot_schema: str
    registry_schema: str
    store: str
    sqlite_user_version: int
    python_minimum: str
    runtime_dependencies: tuple[str, ...]
    schemas: tuple[tuple[str, str], ...]
    capabilities: tuple[str, ...]

    def _validate(self) -> None:
        require(self == version_info_unchecked(), "public version/catalog mismatch")


def version_info_unchecked() -> VersionInfo:
    # Compare a field tuple without recursively constructing another validated instance.
    from afre import version

    value = object.__new__(VersionInfo)
    values = {
        "engine": version.ENGINE_VERSION,
        "api": "1.0",
        "snapshot_schema": "1.0",
        "registry_schema": "1.0",
        "store": version.STORE_SCHEMA_VERSION,
        "sqlite_user_version": version.STORE_USER_VERSION,
        "python_minimum": "3.11",
        "runtime_dependencies": (),
        "capabilities": CAPABILITIES,
        "schemas": tuple(
            sorted(
                (name.removesuffix("_SCHEMA_VERSION").lower(), val)
                for name, val in vars(version).items()
                if name.endswith("_SCHEMA_VERSION")
                and not name.startswith("LEGACY")
                and name != "STORE_SCHEMA_VERSION"
            )
        ),
    }
    for key, val in values.items():
        object.__setattr__(value, key, val)
    return value


def version_info() -> VersionInfo:
    value = version_info_unchecked()
    value.__post_init__()
    return value
