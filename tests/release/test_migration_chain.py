"""Real constructors migrate every historical schema with nonempty preserved native rows."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from afre.calibration import CalibrationRepository
from afre.challenger import ChallengeRepository
from afre.costs import CostResearchRepository
from afre.cross_sectional import CrossSectionRepository
from afre.event_conditioned import EventRepository
from afre.feature_store import FeatureStoreRepository
from afre.fusion import FusionRepository
from afre.health import HealthRepository
from afre.invariance import InvarianceRepository
from afre.mixture import MixtureRepository
from afre.multihorizon import MultiHorizonRepository
from afre.multiple_testing import MultipleTestingRepository
from afre.nonlinear import NonlinearRepository
from afre.orthogonalization import OrthogonalizationRepository
from afre.persistence import ArtifactStore
from afre.probabilistic import ProbabilisticRepository
from afre.regime_conditioned import RegimeRepository
from afre.research_datasets import DatasetRepository
from afre.schema import ContractError
from afre.selection import SelectionRepository
from afre.sequence import SequenceRepository
from afre.service import ServiceRepository
from afre.statistical_models import ModelRepository
from afre.target_engine import TargetRepository
from afre.uncertainty import UncertaintyRepository
from afre.universe import UniverseRepository
from examples.feature_store_demo import SOURCE, definition, source_vintage

REPOSITORIES = (
    ArtifactStore,
    FeatureStoreRepository,
    TargetRepository,
    UniverseRepository,
    DatasetRepository,
    ModelRepository,
    ProbabilisticRepository,
    CalibrationRepository,
    MultiHorizonRepository,
    CrossSectionRepository,
    EventRepository,
    RegimeRepository,
    MixtureRepository,
    NonlinearRepository,
    SequenceRepository,
    UncertaintyRepository,
    OrthogonalizationRepository,
    InvarianceRepository,
    CostResearchRepository,
    MultipleTestingRepository,
    SelectionRepository,
    FusionRepository,
    HealthRepository,
    ChallengeRepository,
    ServiceRepository,
)


def state(connection: sqlite3.Connection) -> dict[str, tuple[tuple[object, ...], ...]]:
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    # Names come only from validated fixed SQLite layout, never from consumer input.
    return {
        name: tuple(connection.execute(f'SELECT * FROM "{name}" ORDER BY 1'))
        for (name,) in tables
    }


def test_entire_nonempty_migration_chain(tmp_path: Path) -> None:
    path = tmp_path / "chain.sqlite"
    feature = definition("market.migration_audit")
    prior: dict[str, tuple[tuple[object, ...], ...]] = {}
    ddl: dict[str, str] = {}
    metadata: dict[str, str] = {}
    for number, cls in enumerate(REPOSITORIES, 1):
        with cls(path) as repo:
            assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == number
            current = state(repo._connection)
            assert all(current[k] == value for k, value in prior.items() if k != "metadata")
            current_ddl = dict(repo._connection.execute("SELECT name,sql FROM sqlite_master"))
            assert all(current_ddl[k] == value for k, value in ddl.items())
            current_meta = dict(repo._connection.execute("SELECT key,value FROM metadata"))
            assert all(current_meta[k] == value for k, value in metadata.items())
            if number == 1:
                with repo.transaction():
                    repo.put(feature.definition)
            if number == 2:
                with repo.transaction():
                    repo.put(SOURCE)
                    repo.put(feature)
                    repo.put(source_vintage(feature, 10, 10))
            assert (
                repo.get(type(feature.definition), feature.definition.fingerprint)
                == feature.definition
            )
            prior, ddl, metadata = state(repo._connection), current_ddl, current_meta
    with ServiceRepository(path) as reopened:
        assert state(reopened._connection) == prior
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=26")
    with pytest.raises(ContractError, match="future"):
        ServiceRepository(path)


def test_nonempty_migration_rollback(tmp_path: Path) -> None:
    path = tmp_path / "rollback.sqlite"
    feature = definition("market.rollback_audit")
    with ChallengeRepository(path) as repo:
        with repo.transaction():
            repo.put(feature.definition)
        frozen = state(repo._connection)
        ddl = tuple(
            repo._connection.execute("SELECT name,sql FROM sqlite_master ORDER BY name")
        )
    with (
        patch(
            "afre.service.repository.service_schema",
            return_value=("CREATE TABLE rollback_probe(x TEXT)", "INVALID DDL"),
        ),
        pytest.raises(sqlite3.Error),
    ):
        ServiceRepository(path)
    with ChallengeRepository(path) as repo:
        assert state(repo._connection) == frozen
        assert (
            tuple(repo._connection.execute("SELECT name,sql FROM sqlite_master ORDER BY name"))
            == ddl
        )
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 24
