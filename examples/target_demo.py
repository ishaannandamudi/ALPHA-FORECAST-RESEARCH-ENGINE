"""Deterministic offline AFRE-2 target truth demonstration with synthetic data."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.datasets import AdjustmentBasis, AdjustmentPolicy
from afre.feature_store.providers import BarTimestampConvention
from afre.features import DataQuality
from afre.horizons import ForecastHorizon, HorizonBasis
from afre.serialization import canonical_json
from afre.target_engine import (
    BenchmarkReference,
    SuppliedBenchmarkReturn,
    TargetActionKind,
    TargetActionStream,
    TargetBar,
    TargetCalendar,
    TargetCorporateAction,
    TargetDefinition,
    TargetEndpointRules,
    TargetEngine,
    TargetMarketSource,
    TargetPathPolicy,
    TargetRepository,
    TargetSession,
    TargetSetManifest,
    target_known_by_cutoff,
)
from afre.target_engine.schema import TargetAggregation, TargetObservationState
from afre.targets import TargetType
from afre.time import TimeRange
from examples.feature_store_demo import (
    CALENDAR,
    INPUT_ID,
    SECURITY,
    SOURCE,
    UNIVERSE,
    clocks,
    origin,
)

SOURCE_MARKET = TargetMarketSource(
    SOURCE, "target-input-build-v1", CALENDAR, "one-unit-bars-v1", 1, "currency"
)
CALENDAR_TARGET = TargetCalendar(
    CALENDAR,
    "synthetic-calendar-v1",
    "UTC",
    (TargetSession("synthetic-session-v1", TimeRange(0, 1000)),),
    clocks(0),
    SOURCE.provenance,
)
BENCHMARK = BenchmarkReference(SECURITY, INPUT_ID, "supplied-neutral-benchmark", "supplied-v1")


def definition(
    kind: TargetType = TargetType.SIMPLE_RETURN,
    horizon_ns: int = 4,
    adjustment: AdjustmentPolicy | None = None,
) -> TargetDefinition:
    mapping = {
        TargetType.SIMPLE_RETURN: TargetAggregation.SIMPLE,
        TargetType.LOG_RETURN: TargetAggregation.LOG,
        TargetType.RESIDUAL_RETURN: TargetAggregation.RESIDUAL,
        TargetType.ABSOLUTE_RETURN: TargetAggregation.ABSOLUTE,
        TargetType.REALIZED_VOLATILITY: TargetAggregation.VOLATILITY,
        TargetType.DOWNSIDE_RETURN: TargetAggregation.DOWNSIDE,
        TargetType.MAX_ADVERSE_EXCURSION: TargetAggregation.ADVERSE,
        TargetType.MAX_FAVORABLE_EXCURSION: TargetAggregation.FAVORABLE,
    }
    path = (
        TargetPathPolicy(1)
        if kind
        in (
            TargetType.REALIZED_VOLATILITY,
            TargetType.MAX_ADVERSE_EXCURSION,
            TargetType.MAX_FAVORABLE_EXCURSION,
        )
        else None
    )
    return TargetDefinition(
        "target." + kind.value,
        "1",
        kind,
        ForecastHorizon(HorizonBasis.ELAPSED_TIME, duration_ns=horizon_ns),
        TargetEndpointRules(),
        adjustment or AdjustmentPolicy(AdjustmentBasis.RAW, 0),
        mapping[kind],
        (INPUT_ID,),
        CALENDAR,
        SOURCE_MARKET.bar_definition,
        BENCHMARK if kind is TargetType.RESIDUAL_RETURN else None,
        path,
    )


def bar(at_ns: int, price: float, available_ns: int | None = None) -> TargetBar:
    return TargetBar(
        SECURITY,
        TimeRange(at_ns - 1, at_ns),
        at_ns,
        BarTimestampConvention.END_EXCLUSIVE,
        "synthetic-session-v1",
        price,
        TargetObservationState.VALID,
        DataQuality.VERIFIED,
        SOURCE_MARKET,
        clocks(at_ns if available_ns is None else available_ns),
    )


def register_sources(repository: TargetRepository) -> None:
    with repository.transaction():
        repository.put(SOURCE)
        repository.put(SOURCE_MARKET)
        repository.put(CALENDAR_TARGET)
        repository.put(BENCHMARK)


def populate(repository: TargetRepository) -> tuple[TargetEngine, TargetSetManifest, str]:
    register_sources(repository)
    engine = TargetEngine(repository)
    observations = tuple(
        bar(at, price, at + 2)
        for at, price in ((1, 100.0), (2, 102.0), (3, 98.0), (4, 104.0), (5, 105.0))
    )
    benchmark = SuppliedBenchmarkReturn(
        BENCHMARK, TimeRange(1, 5), 1, 5, 0.02, clocks(8), SOURCE.provenance
    )
    with repository.transaction():
        for observation in observations:
            repository.put(observation)
        repository.put(benchmark)
    source_build = engine.freeze_source(
        SOURCE_MARKET, CALENDAR_TARGET, 8, benchmark_ids=(benchmark.fingerprint,)
    )
    targets = TargetSetManifest(tuple(definition(kind) for kind in TargetType))
    manifest = engine.build_dataset(
        "offline-target-demo",
        (origin(1),),
        targets,
        source_build.fingerprint,
        UNIVERSE,
        clocks(8),
    )
    return engine, targets, manifest.fingerprint


def main() -> None:
    with TemporaryDirectory(prefix="afre-target-demo-") as directory:
        path = Path(directory) / "targets.sqlite"
        with TargetRepository(path) as repository:
            engine, targets, manifest_id = populate(repository)
            from afre.target_engine import TargetDatasetManifest

            manifest = repository.get(TargetDatasetManifest, manifest_id)
            frozen = canonical_json(manifest)
            rows = engine.rows(manifest)
            simple = next(
                row for row in rows if row.definition.target_type is TargetType.SIMPLE_RETURN
            )
            assert simple.value is not None and abs(simple.value - 0.05) < 1e-12
            assert not target_known_by_cutoff(simple, 7) and target_known_by_cutoff(simple, 8)
            print("Forward label excluded at origin; same-time training cutoff eligible")
            for row in rows:
                print(row.definition.target_type.value, row.value)
            old_bar = repository.get(TargetBar, simple.endpoint_bar_id or "")
            revised = replace(
                old_bar, close=110.0, clocks=clocks(10), predecessor_id=old_bar.fingerprint
            )
            with repository.transaction():
                repository.put(revised)
            # Residual benchmark data remains pinned explicitly in the new build.
            from afre.target_engine import TargetSourceBuild

            prior_source = repository.get(TargetSourceBuild, manifest.source_build_id)
            new_source = engine.freeze_source(
                SOURCE_MARKET, CALENDAR_TARGET, 10, benchmark_ids=prior_source.benchmark_ids
            )
            rebuilt = engine.build_dataset(
                "offline-target-demo",
                (origin(1),),
                targets,
                new_source.fingerprint,
                UNIVERSE,
                clocks(10),
            )
            assert rebuilt.fingerprint != manifest.fingerprint
            assert canonical_json(repository.get(TargetDatasetManifest, manifest_id)) == frozen
            old_values = tuple(canonical_json(row) for row in rows)
            action = TargetCorporateAction(
                SECURITY,
                "split-2-for-1",
                3,
                TargetActionKind.SPLIT,
                2.0,
                INPUT_ID,
                clocks(8),
                SOURCE.provenance,
            )
            stream = TargetActionStream(
                INPUT_ID,
                "split-stream-v1",
                (action.fingerprint,),
                0,
                10,
                clocks(10),
                SOURCE.provenance,
            )
            with repository.transaction():
                repository.put(action)
                repository.put(stream)
            action_build = engine.freeze_source(SOURCE_MARKET, CALENDAR_TARGET, 10, stream)
            split = replace(
                definition(
                    adjustment=AdjustmentPolicy(AdjustmentBasis.SPLIT_ADJUSTED, 8, INPUT_ID)
                ),
                name="target.split_return",
            )
            split_dataset = engine.build_dataset(
                "split-demo",
                (origin(1),),
                TargetSetManifest((split,)),
                action_build.fingerprint,
                UNIVERSE,
                clocks(10),
            )
            print(
                "RAW and SPLIT_ADJUSTED identities differ:",
                split_dataset.fingerprint != rebuilt.fingerprint,
            )
            audit = engine.audit_target(simple.fingerprint)
            count = engine.audit()
            print(
                "Target audit lineage nodes:",
                len(audit.lineage_ids),
                "validated artifacts:",
                count,
            )
        with TargetRepository(path) as restarted:
            replay = TargetEngine(restarted).rows(
                restarted.get(TargetDatasetManifest, manifest_id)
            )
            assert tuple(canonical_json(row) for row in replay) == old_values
            assert canonical_json(restarted.get(TargetDatasetManifest, manifest_id)) == frozen
        print("Future correction preserves old labels; rebuilt dataset has a new identity")
        print("Byte-identical target restart replay")
        print("Target dataset:", manifest_id)


if __name__ == "__main__":
    main()
