"""One causal session fixture, copied into an isolated immutable registry per test."""

import shutil
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from afre.cross_sectional.engine import CrossSectionEngine
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.schema import SignalQuality
from afre.feature_store.models import AvailabilityEvidence
from afre.nonlinear import NonlinearEngine, ScalarInput
from afre.sequence import (
    SequenceEngine,
    SequenceFeatureDefinition,
    SequenceForecast,
    SequenceObservation,
    SequenceRepository,
)
from examples.sequence_demo import SequenceFixture, build_fixture


@dataclass(frozen=True)
class Base:
    path: Path
    fixture: SequenceFixture


@pytest.fixture(scope="session")
def base(tmp_path_factory: pytest.TempPathFactory) -> Base:
    path = tmp_path_factory.mktemp("sequence-session") / "base.sqlite"
    with SequenceRepository(path) as repo:
        fixture = build_fixture(repo)
    return Base(path, fixture)


@dataclass
class Case:
    repo: SequenceRepository
    fixture: SequenceFixture

    @property
    def engine(self) -> SequenceEngine:
        return SequenceEngine(self.repo)

    @property
    def forecast(self) -> SequenceForecast:
        return self.repo.get(SequenceForecast, self.fixture.forecasts[0][0])

    @property
    def micro(self) -> SequenceFeatureDefinition:
        from afre.nonlinear.definitions import ScalarFeatureDefinition

        return next(
            f
            for f in self.fixture.features
            if f.source_definition_id.startswith("afre.nl_feature:")
            and (d := self.repo.get(ScalarFeatureDefinition, f.source_definition_id)).kind.value
            == "external_signal"
            and d.source_key[3] == "microstructure.signal"
        )

    def observe(
        self,
        at: int,
        number: float | None,
        received: int | None = None,
        quality: SignalQuality | None = None,
    ) -> SequenceObservation:
        origin = self.forecast.origin
        row = self.repo._connection.execute(
            "SELECT fingerprint FROM sq_records WHERE feature_id=? AND security_id=? "
            "ORDER BY origin_ns LIMIT 1",
            (self.micro.fingerprint, origin.instrument.fingerprint),
        ).fetchone()
        assert row is not None
        old = self.repo.get(SequenceObservation, row[0])
        scalar = self.repo.get(ScalarInput, old.source_id)
        source = self.repo.get(ExternalSignal, scalar.source_id)
        received = at if received is None else received
        source = replace(
            source,
            as_of_ns=at,
            value=number,
            quality=quality
            or (SignalQuality.MISSING if number is None else SignalQuality.VALID),
            clocks=AvailabilityEvidence(received, received, received, received, at, at),
        )
        CrossSectionEngine(self.repo).publish_external(source)
        scalar = NonlinearEngine(self.repo).scalar(
            source.fingerprint,
            replace(origin, timestamp_ns=received, availability_cutoff_ns=received),
        )
        return self.engine.observation(self.micro, scalar.fingerprint)


@pytest.fixture
def case(base: Base, tmp_path: Path) -> Iterator[Case]:
    path = tmp_path / "sequence.sqlite"
    shutil.copy2(base.path, path)
    with SequenceRepository(path) as repo:
        yield Case(repo, base.fixture)
