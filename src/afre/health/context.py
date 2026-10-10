"""Pinned native context certificates without decoding research outcomes on drift paths."""

import json
from typing import TYPE_CHECKING

from afre.fusion.accounting import FusionTrialPool
from afre.hashing import bytes_digest
from afre.multiple_testing.evaluations import FamilyAnalysis
from afre.multiple_testing.families import HypothesisFamily
from afre.multiple_testing.test_reuse import TestReuseDiagnostic
from afre.multiple_testing.trials import ResearchTrial
from afre.research_datasets.splits import TestEvaluation
from afre.schema import Artifact, require
from afre.selection.results import SelectionResult
from afre.serialization import canonical_json

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository

CLASSES: tuple[type[Artifact], ...] = (
    ResearchTrial,
    HypothesisFamily,
    FamilyAnalysis,
    TestEvaluation,
    TestReuseDiagnostic,
    SelectionResult,
    FusionTrialPool,
)


def context_records(
    repo: "HealthRepository", identities: tuple[str, ...]
) -> tuple[tuple[str, str, int, str], ...]:
    require(
        not repo._feature_only_depth,
        "context certificates declared outside target-free monitoring",
    )
    records = []
    for identity in sorted(identities):
        cls = next((c for c in CLASSES if identity.startswith("afre." + c.domain + ":")), None)
        require(cls is not None, "health closed research/TEST context")
        assert cls is not None
        value = repo.get(cls, identity)
        at = getattr(
            value,
            "available_ns",
            getattr(
                value,
                "completed_ns",
                getattr(value, "evaluated_ns", getattr(value, "declared_ns", 0)),
            ),
        )
        records.append(
            (identity, cls.__name__, at, bytes_digest(canonical_json(value).encode()))
        )
    return tuple(records)


def verify_context(
    repo: "HealthRepository", records: tuple[tuple[str, str, int, str], ...]
) -> None:
    # Fixed native artifact tables, never provider-selected SQL identifiers. Read
    # bounded canonical bytes and certify the declared digest without decoding
    # TrialObservation outcomes or weakening native planned-registration guards.
    tables = {
        "ResearchTrial": "mt_artifacts",
        "HypothesisFamily": "mt_artifacts",
        "FamilyAnalysis": "mt_artifacts",
        "TestReuseDiagnostic": "mt_artifacts",
        "SelectionResult": "sel_artifacts",
        "FusionTrialPool": "fus_artifacts",
        "TestEvaluation": "r_artifacts",
    }
    for identity, kind, at, digest in records:
        require(kind in tables, "health closed context certificate type")
        table = tables[kind]
        row = repo._connection.execute(
            "SELECT type_name,schema_version,CASE WHEN length(CAST(payload AS BLOB))<=? "
            f"THEN payload ELSE NULL END FROM {table} WHERE fingerprint=?",
            (repo.health_bounds.payload_bytes, identity),
        ).fetchone()
        require(
            row is not None
            and row[:2] == (kind, "1.0")
            and type(row[2]) is str
            and bytes_digest(row[2].encode()) == digest
            and identity
            == "afre."
            + identity.split(":")[0][5:]
            + ":1.0:"
            + bytes_digest(
                ("AFRE\x001.0\x00" + identity.split(":")[0][5:] + "\x00").encode()
                + row[2].encode()
            ),
            "health native context certificate corruption/bound",
        )
        fields = json.loads(row[2])["artifact"]["fields"]
        clock = next(
            (
                fields[n]
                for n in ("available_ns", "completed_ns", "evaluated_ns", "declared_ns")
                if n in fields
            ),
            0,
        )
        require(
            type(clock) is int and clock == at, "health exact native context clock certificate"
        )
