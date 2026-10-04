"""Deterministic offline AFRE-4 walkthrough, including revisions and restart replay."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.feature_store import FeatureSetManifest, NormalizationSpec
from afre.feature_store.normalization import NormalizationMethod
from afre.forecast import ForecastOrigin
from afre.ids import InstrumentId
from afre.research_datasets import (
    DatasetCompatibility,
    DatasetEngine,
    DatasetRepository,
    EmbargoDirection,
    EmbargoPolicy,
    FoldPreprocessingSpec,
    Partition,
    ResearchDatasetDefinition,
    ResearchDatasetManifest,
    ResearchOriginRequest,
    SampleState,
    SplitDefinition,
    SplitStrategy,
    ZeroScaleRule,
)
from afre.serialization import canonical_json
from afre.target_engine import TargetEngine, TargetSetManifest
from afre.time import TimeRange
from afre.universe import (
    ConstituentCoverage,
    EligibilityPolicy,
    IssuerRecord,
    LifecycleEvent,
    ListingRecord,
    SecurityRecord,
    SymbolAssignment,
    TradabilityRecord,
    UniverseCalendar,
    UniverseDefinition,
    UniverseEngine,
    UniverseMembershipVintage,
    UniverseSession,
)
from afre.universe.schema import (
    LifecycleKind,
    MembershipState,
    SecurityType,
    SnapshotCompleteness,
    TradabilityState,
    UniverseSourceKind,
)
from afre.universe.validation import to_universe_manifest
from examples.feature_store_demo import (
    BUILD,
    CALENDAR,
    INPUT_ID,
    SOURCE,
    clocks,
    definition,
    source_vintage,
)
from examples.target_demo import CALENDAR_TARGET, SOURCE_MARKET, bar
from examples.target_demo import definition as target_definition
from examples.universe_demo import SECURITIES, evidence


@dataclass(frozen=True)
class ResearchFixture:
    definition: ResearchDatasetDefinition
    requests: tuple[ResearchOriginRequest, ...]
    preprocessing: FoldPreprocessingSpec


def populate(
    repository: DatasetRepository,
    reverse: bool = False,
    validation_outlier: float = 1000.0,
    missing: bool = True,
    security_count: int = 4,
) -> ResearchFixture:
    from afre.universe.identity import ListingId, StableIssuerId, StableSecurityId

    securities = tuple(
        StableSecurityId("synthetic-security", f"{i + 1:04d}") for i in range(security_count)
    )
    issuers = tuple(
        StableIssuerId("synthetic-issuer", f"{i + 1:04d}") for i in range(security_count)
    )
    listings = tuple(
        ListingId("synthetic-listing", f"{i + 1:04d}") for i in range(security_count)
    )
    feature = definition("market.research_value", lookback_ns=4)
    calendar = UniverseCalendar(
        CALENDAR,
        "research-calendar-v1",
        "XTEST",
        "UTC",
        tuple(
            UniverseSession(f"session-{start}", TimeRange(start, end))
            for start, end in (
                (0, 10),
                (20, 30),
                (40, 50),
                (60, 65),
                (70, 80),
                (90, 100),
                (110, 120),
            )
        ),
        evidence(InstrumentId("calendar", "research")),
    )
    universe = UniverseDefinition(
        "universe.research",
        "1",
        UniverseSourceKind.INDEX_MEMBERSHIP,
        SOURCE,
        EligibilityPolicy(),
        calendar,
    )
    targets = TargetSetManifest(
        tuple(
            replace(target_definition(horizon_ns=horizon), name=f"target.return_{horizon}")
            for horizon in (5, 15)
        )
    )
    ordering = (
        tuple(reversed(range(security_count))) if reverse else tuple(range(security_count))
    )
    origins = tuple(range(10, 81, 10))
    with repository.transaction(), repository.validation_cache():
        for initial in (SOURCE, feature, calendar, SOURCE_MARKET, CALENDAR_TARGET):
            repository.put(initial)
        for index in ordering:
            security = securities[index]
            repository.put(
                IssuerRecord(issuers[index], "US", evidence(issuers[index].instrument))
            )
            repository.put(
                SecurityRecord(
                    security,
                    issuers[index],
                    SecurityType.COMMON_STOCK,
                    "A",
                    "equity",
                    "USD",
                    "US",
                    evidence(security.instrument),
                )
            )
            start, end = (60, 1000) if index == 3 else (0, 60 if index == 2 else 1000)
            repository.put(
                ListingRecord(
                    listings[index],
                    security,
                    "XTEST",
                    "USD",
                    True,
                    CALENDAR,
                    evidence(security.instrument, start, end),
                )
            )
            repository.put(
                TradabilityRecord(
                    listings[index],
                    security,
                    TradabilityState.TRADABLE,
                    evidence(security.instrument, start, end),
                )
            )
            repository.put(
                SymbolAssignment(
                    listings[index],
                    security,
                    "REUSED" if index >= 2 else f"S{index}",
                    "XTEST",
                    evidence(security.instrument, start, end),
                )
            )
        repository.put(universe)
        repository.put(
            ConstituentCoverage(
                universe.fingerprint,
                securities,
                SnapshotCompleteness.COMPLETE,
                evidence(InstrumentId("universe", "research")),
            )
        )
        for index in ordering:
            security = securities[index]
            windows = (
                ((0, 60, MembershipState.INCLUDED), (60, 1000, MembershipState.EXCLUDED))
                if index == 2
                else (
                    ((0, 60, MembershipState.EXCLUDED), (60, 1000, MembershipState.INCLUDED))
                    if index == 3
                    else ((0, 1000, MembershipState.INCLUDED),)
                )
            )
            for start, end, state in windows:
                repository.put(
                    UniverseMembershipVintage(
                        universe.fingerprint,
                        security,
                        state,
                        evidence(security.instrument, start, end),
                    )
                )
            feature_times = tuple(reversed(origins)) if reverse else origins
            for at in feature_times:
                # An absent early feature stays explicit until the first received vintage.
                if missing and index == 1 and at == 10:
                    continue
                value = validation_outlier + index if at >= 40 else float(at + index)
                repository.put(
                    source_vintage(feature, at, at, value, entity=security.instrument)
                )
            bar_times = tuple(reversed(range(1, 101))) if reverse else tuple(range(1, 101))
            for at in bar_times:
                if index == 2 and at >= 60:
                    continue
                repository.put(
                    replace(bar(at, 100.0 + at + index), instrument=security.instrument)
                )
        repository.put(
            LifecycleEvent(
                security=securities[2],
                event_id="research-delisting",
                kind=LifecycleKind.DELISTING,
                description="Synthetic delisting with absent subsequent target observations",
                evidence=evidence(securities[2].instrument, 60, 1000, 60),
            )
        )
        repository.put(FeatureSetManifest((feature,)))
        for target in targets.definitions:
            repository.put(target)
        repository.put(targets)
    engine = UniverseEngine(repository)
    label_engine = TargetEngine(repository)
    requests = []
    for at in origins:
        snapshot = engine.universe_as_of(universe, at, at)
        engine.persist_snapshot(snapshot)
        manifest = to_universe_manifest(snapshot)
        origin_rows = tuple(
            ForecastOrigin(
                member.instrument, at, at, "synthetic-session-v1", BUILD, manifest.fingerprint
            )
            for member in manifest.memberships
        )
        source = label_engine.freeze_source(SOURCE_MARKET, CALENDAR_TARGET, at + 15)
        labels = label_engine.build_dataset(
            "research-targets",
            origin_rows,
            targets,
            source.fingerprint,
            manifest,
            clocks(at + 15),
        )
        requests.append(
            ResearchOriginRequest(
                snapshot.fingerprint, "synthetic-session-v1", BUILD, labels.fingerprint
            )
        )
    compatibility = DatasetCompatibility(
        (INPUT_ID,),
        CALENDAR,
        (calendar.fingerprint,),
        (CALENDAR_TARGET.fingerprint,),
        feature.adjustment,
        (feature.adjustment.fingerprint,),
    )
    dataset_definition = ResearchDatasetDefinition(
        "research.synthetic", "1", FeatureSetManifest((feature,)), targets, compatibility
    )
    preprocessing = FoldPreprocessingSpec(
        NormalizationSpec(
            feature, NormalizationMethod.STANDARDIZE, "afre-fold-preprocessing-v1"
        ),
        ZeroScaleRule.UNIT_SCALE,
    )
    with repository.transaction():
        repository.put(preprocessing)
    return ResearchFixture(dataset_definition, tuple(requests), preprocessing)


def split_definition(fixture: ResearchFixture) -> SplitDefinition:
    return SplitDefinition(
        "split.walk_forward",
        "1",
        SplitStrategy.WALK_FORWARD,
        TimeRange(10, 40),
        TimeRange(40, 50),
        40,
        10,
        3,
        TimeRange(70, 90),
        embargo=EmbargoPolicy(count=10, direction=EmbargoDirection.BEFORE),
        preprocessing_spec_ids=(fixture.preprocessing.fingerprint,),
    )


def main() -> None:
    with TemporaryDirectory(prefix="afre-research-demo-") as directory:
        path = Path(directory) / "research.sqlite"
        with DatasetRepository(path) as repository:
            fixture = populate(repository)
            engine = DatasetEngine(repository)
            dataset = engine.build_dataset(fixture.definition, fixture.requests, 100, 100)
            split = engine.build_split(dataset.fingerprint, split_definition(fixture))
            folds = engine.folds(split.fingerprint)
            states = tuple(
                engine.fit_preprocessing(fold.fingerprint, fixture.preprocessing)
                for fold in folds
            )
            for fold, state in zip(folds, states, strict=True):
                print(
                    "Fold",
                    fold.ordinal,
                    "cutoff",
                    fold.training_cutoff_ns,
                    {
                        p.value: len(engine.partition_samples(fold.fingerprint, p))
                        for p in Partition
                    },
                    "TRAIN statistics",
                    {p.name: p.value for p in state.normalization.parameters},
                )
                engine.audit_fold(fold.fingerprint)
            samples = engine.dataset_samples(dataset.fingerprint)
            assert any(s.state is SampleState.INELIGIBLE for s in samples)
            assert any(s.state is SampleState.FEATURE_INCOMPLETE for s in samples)
            assert any(
                s.security == SECURITIES[2]
                and s.timestamp_ns == 10
                and s.state is SampleState.AVAILABLE
                for s in samples
            )
            frozen = canonical_json(dataset)
            exported = engine.export_rows(dataset.fingerprint, 100)
            old = source_vintage(
                fixture.preprocessing.normalization.feature,
                10,
                10,
                10.0,
                entity=SECURITIES[0].instrument,
            )
            corrected = replace(
                old, value=999.0, clocks=clocks(10), predecessor_id=old.fingerprint
            )
            with repository.transaction():
                repository.put(corrected)
            rebuilt = engine.build_dataset(fixture.definition, fixture.requests, 100, 100)
            assert rebuilt.fingerprint != dataset.fingerprint
            assert engine.export_rows(dataset.fingerprint, 100) == exported
            engine.audit_dataset(dataset.fingerprint)
            test, evaluation = engine.test_samples_for_fold(
                folds[-1].fingerprint,
                "offline-evaluation-v1",
                "explicit final holdout evaluation",
                100,
            )
            print("Sealed TEST ready", len(test), "evaluation", evaluation.fingerprint)
            repository.audit()
            print(
                "Frozen revision preserved; corrected build has new identity",
                rebuilt.fingerprint,
            )
        with DatasetRepository(path) as repository:
            assert (
                canonical_json(repository.get(ResearchDatasetManifest, dataset.fingerprint))
                == frozen
            )
            assert DatasetEngine(repository).export_rows(dataset.fingerprint, 100) == exported
            repository.audit()
        print(
            "PASS: exact grid, cutoff, purge/embargo, TRAIN statistics, audit, "
            "revision and restart"
        )


if __name__ == "__main__":
    main()
