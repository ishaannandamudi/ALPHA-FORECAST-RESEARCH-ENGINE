"""Deterministic package manifest; mutable reports/timings are outside source identity."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from afre.service import __all__ as service_exports
from afre.service.versions import version_info

ROOT = Path(__file__).resolve().parents[1]


def source_identity() -> tuple[str, dict[str, str]]:
    paths = sorted((*ROOT.joinpath("src/afre").rglob("*.py"), ROOT / "pyproject.toml"))
    hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths
    }
    digest = hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return digest, hashes


def manifest(status: str) -> dict[str, object]:
    if status not in ("BLOCKED", "RELEASE_CANDIDATE"):
        raise ValueError("closed release decision")
    info = version_info()
    digest, hashes = source_identity()
    return {
        "engine": info.engine,
        "service_api": info.api,
        "public_schemas": dict(info.schemas),
        "store": info.store,
        "sqlite_user_version": info.sqlite_user_version,
        "sqlite_library_version": sqlite3.sqlite_version,
        "python_minimum": info.python_minimum,
        "runtime_dependencies": [],
        "capabilities": list(info.capabilities),
        "release_status": status,
        "package": "alpha-forecast-research-engine",
        "source_identity": {
            "algorithm": "SHA256",
            "digest": digest,
            "files": hashes,
            "scope": (
                "src/afre/**/*.py and pyproject.toml; canonical sorted compact UTF-8 JSON "
                "of path-to-SHA256 map"
            ),
        },
        "public_service_exports": service_exports,
        "supported_snapshot_engines": ["0.25.0", "1.0.0"],
        "reproducibility_scope": (
            "identical evidence, versions, declared seeds/cutoffs/folds, "
            "Python/platform floating environment; four hash seeds and reversed input "
            "orders; no cross-hardware bit promise"
        ),
        "excluded_diagnostics": [
            "wall-clock timings",
            "SQLite page layout",
            "benchmark measurements",
        ],
        "unsupported_capabilities": [
            "EXECUTION",
            "PORTFOLIO",
            "RISK_OPTIMIZATION",
            "AUTOMATIC_TRAINING",
            "AUTOMATIC_CALIBRATION",
            "AUTOMATIC_PROMOTION",
            "ACTIVE_MODEL_POINTER",
            "JOINT_HORIZON_LAW",
            "QUANTILE_ONLY_DENSITY",
        ],
        "security_boundaries": [
            "closed data-only JSON",
            "bounded immutable SQLite artifacts",
            "no network or executable payloads",
            "caller-selected store path only",
            "source attestation is an external trust assumption",
        ],
        "downstream_contract": (
            "stable security IDs, UTC nanoseconds, exact availability and provenance, "
            "target/horizon units, exact snapshot identity and native law; portfolio, "
            "risk optimization and execution are downstream"
        ),
        "store_rationale": (
            "No schema-26 migration: release documents, manifest and audits require "
            "no new persisted research contract. SQLite25/store1.24 preserve all "
            "immutable prior metadata, including service_engine_version=0.25.0 as "
            "schema-creation provenance rather than current engine."
        ),
        "release_meaning": (
            "Audited research architecture; no production deployment, realized alpha "
            "or profitability guarantee"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", choices=("BLOCKED", "RELEASE_CANDIDATE"), default="BLOCKED")
    args = parser.parse_args()
    destination = ROOT / "docs/afre-release-manifest.json"
    destination.write_text(json.dumps(manifest(args.status), sort_keys=True, indent=2) + "\n")
    print(f"Wrote deterministic manifest: {args.status}")


if __name__ == "__main__":
    main()
