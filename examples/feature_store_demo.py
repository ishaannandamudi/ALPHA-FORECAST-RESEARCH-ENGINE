"""Deterministic offline AFRE-1 walkthrough, using synthetic received information."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.datasets import (
    AdjustmentBasis,
    AdjustmentPolicy,
    DatasetManifest,
    UniverseManifest,
    UniverseMembership,
    UniversePolicy,
)
from afre.feature_store import (
    AvailabilityEvidence,
    FeatureComputationGraph,
    FeatureComputationSpec,
    FeatureSetManifest,
    FeatureStore,
    FeatureStoreRepository,
    FeatureVintage,
    NormalizationSpec,
    NormalizationState,
    RegisteredFeatureDefinition,
    SourceReference,
)
from afre.feature_store.computation import IMPLEMENTATION_VERSION
from afre.feature_store.dag import MissingInputPolicy, Transformation, WindowBasis
from afre.feature_store.freshness import FreshnessPolicy
from afre.feature_store.normalization import NormalizationMethod
from afre.feature_store.providers import (
    BarTimestampConvention,
    EIEFeatureAdapter,
    MarketBar,
    MarketFeatureAdapter,
    SuppliedEIEFeatures,
)
from afre.feature_store.schema import StoreScope, ValidityRule
from afre.features import (
    AvailabilityRule,
    DataQuality,
    FeatureDefinition,
    FeatureScope,
    FeatureSemantic,
    FeatureSet,
    MissingPolicy,
    MissingState,
    ValueType,
)
from afre.forecast import ForecastOrigin
from afre.hashing import bytes_digest
from afre.horizons import ForecastHorizon, HorizonBasis
from afre.ids import InstrumentId
from afre.lineage import Parameter, ProvenanceRef
from afre.providers import EventSnapshotRef
from afre.serialization import canonical_json
from afre.targets import TargetSpec, TargetType
from afre.time import DAY_NS, SECOND_NS, TimeRange

SECURITY = InstrumentId("synthetic-security", "0001")
INPUT_ID = ProvenanceRef(
    "offline-fixture", "input-dataset-v1", "1", bytes_digest(b"inputs")
).fingerprint
SOURCE = SourceReference(
    ProvenanceRef("offline-fixture", "source-v1", "1", bytes_digest(b"source")), INPUT_ID
)
CALENDAR = "synthetic-calendar-v1"
BUILD = "demo-build-v1"
UNIVERSE = UniverseManifest(
    "historical-demo",
    "synthetic-membership-v1",
    "eligibility-v1",
    UniversePolicy.POINT_IN_TIME,
    (UniverseMembership(SECURITY, TimeRange(0, DAY_NS), 0, "synthetic"),),
)


def origin(timestamp_ns: int, instrument: InstrumentId = SECURITY) -> ForecastOrigin:
    return ForecastOrigin(
        instrument,
        timestamp_ns,
        timestamp_ns,
        "synthetic-session-v1",
        BUILD,
        UNIVERSE.fingerprint,
    )


def definition(
    name: str = "market.close",
    unit: str = "currency",
    dependencies: tuple[RegisteredFeatureDefinition, ...] = (),
    lookback_ns: int = 300 * SECOND_NS,
) -> RegisteredFeatureDefinition:
    core = FeatureDefinition(
        name,
        "1",
        FeatureSemantic.EVENT if name.startswith("eie.") else FeatureSemantic.MARKET,
        ValueType.NUMBER,
        unit,
        FeatureScope.INSTRUMENT,
        lookback_ns,
        AvailabilityRule.COMPUTED if dependencies else AvailabilityRule.SOURCE_PUBLICATION,
        MissingPolicy.EXPLICIT_STATE,
        "transform-v1" if dependencies else "source-v1",
        tuple(item.definition.fingerprint for item in dependencies),
    )
    return RegisteredFeatureDefinition(
        core,
        StoreScope.SECURITY,
        FreshnessPolicy(),
        ValidityRule.LAST_OBSERVATION,
        CALENDAR,
        BUILD,
        AdjustmentPolicy(AdjustmentBasis.RAW, 0),
        (INPUT_ID,),
    )


def clocks(timestamp_ns: int) -> AvailabilityEvidence:
    return AvailabilityEvidence(timestamp_ns, timestamp_ns, timestamp_ns, timestamp_ns)


def source_vintage(
    feature: RegisteredFeatureDefinition,
    effective_ns: int,
    available_ns: int,
    value: float = 100.0,
    source: SourceReference = SOURCE,
    entity: InstrumentId = SECURITY,
) -> FeatureVintage:
    return FeatureVintage(
        feature,
        entity,
        effective_ns,
        clocks(available_ns),
        source,
        value,
        MissingState.PRESENT,
        DataQuality.VERIFIED,
    )


def dataset(features: FeatureSetManifest) -> DatasetManifest:
    target = TargetSpec(
        TargetType.SIMPLE_RETURN,
        ForecastHorizon(HorizonBasis.ELAPSED_TIME, duration_ns=DAY_NS),
        "ratio",
        "contract-only-v1",
    )
    return DatasetManifest(
        "feature-store-demo",
        TimeRange(0, DAY_NS),
        UNIVERSE,
        FeatureSet(tuple(item.definition for item in features.definitions)),
        (target,),
        (INPUT_ID,),
        CALENDAR,
        AdjustmentPolicy(AdjustmentBasis.RAW, 0),
        MissingPolicy.EXPLICIT_STATE,
        "feature-store-demo-v1",
        engine_version="0.2.0",
    )


def computation(
    output: RegisteredFeatureDefinition,
    inputs: tuple[RegisteredFeatureDefinition, ...],
    transformation: Transformation,
    minimum: int = 1,
    window: WindowBasis = WindowBasis.LATEST_VALUES,
    normalization_state_id: str | None = None,
) -> FeatureComputationSpec:
    return FeatureComputationSpec(
        output,
        inputs,
        transformation,
        "transform-v1",
        IMPLEMENTATION_VERSION,
        minimum,
        MissingInputPolicy.REJECT,
        window_basis=window,
        normalization_state_id=normalization_state_id,
    )


def populate(repository: FeatureStoreRepository) -> tuple[FeatureStore, FeatureSetManifest]:
    store = FeatureStore(repository)
    close = definition()
    returns = definition("market.return_5m", "ratio", (close,))
    volatility = definition("market.trailing_vol", "ratio", (returns,))
    event = definition("eie.event_materiality", "ratio")
    normalized = definition("market.return_zscore", "ratio", (returns,))
    features = FeatureSetManifest((close, returns, volatility, event, normalized))
    with repository.transaction():
        repository.put(SOURCE)
        for feature in features.definitions:
            store.registry.register_definition(feature)
        repository.put(features)
        graph = FeatureComputationGraph(features.definitions)
        repository.put(graph)
        for minute, price in ((1, 100.0), (2, 101.0), (3, 102.0)):
            end = minute * 60 * SECOND_NS
            bar = MarketBar(
                SECURITY,
                TimeRange(end - 60 * SECOND_NS, end),
                end,
                BarTimestampConvention.END_EXCLUSIVE,
                price,
                1000.0,
                clocks(end + SECOND_NS),
                SOURCE,
                close.adjustment,
                CALENDAR,
                BUILD,
            )
            repository.put(bar)
            vintage = MarketFeatureAdapter().extract(bar, close)
            repository.put(vintage.source)
            store.append_vintage(vintage)
        snapshot = EventSnapshotRef(
            SECURITY,
            "eie-final-snapshot-v1",
            170 * SECOND_NS,
            170 * SECOND_NS,
            "external-eie-v1",
            ("snapshot-1.0",),
            (SOURCE.provenance,),
        )
        supplied = SuppliedEIEFeatures(
            snapshot, 170 * SECOND_NS, 0.7, 0.3, 0.2, ("source_uncertain",)
        )
        repository.put(supplied)
        vintage = EIEFeatureAdapter().extract(
            supplied,
            event,
            AvailabilityEvidence(
                172 * SECOND_NS,
                173 * SECOND_NS,
                173 * SECOND_NS,
                173 * SECOND_NS,
                170 * SECOND_NS,
                170 * SECOND_NS,
            ),
            INPUT_ID,
        )
        repository.put(vintage.source)
        store.append_vintage(vintage)
    return_spec = computation(
        returns, (close,), Transformation.PERCENT_CHANGE, 2, WindowBasis.ELAPSED_LOOKBACK
    )
    fit_sample = []
    for timestamp in (121 * SECOND_NS, 181 * SECOND_NS):
        value, _ = store.compute(return_spec, origin(timestamp), clocks(timestamp))
        fit_sample.append(value)
    vol_spec = computation(
        volatility, (returns,), Transformation.ROLLING_STDDEV, 2, WindowBasis.ELAPSED_LOOKBACK
    )
    store.compute(vol_spec, origin(181 * SECOND_NS), clocks(181 * SECOND_NS))
    spec = NormalizationSpec(returns, NormalizationMethod.STANDARDIZE, "supplied-fixture-v1")
    state = NormalizationState(
        spec,
        (fit_sample[0].fingerprint,),
        122 * SECOND_NS,
        123 * SECOND_NS,
        (Parameter("mean", 0.01), Parameter("stddev", 0.02)),
        INPUT_ID,
    )
    with repository.transaction():
        repository.put(spec)
        repository.put(state)
    normalized_spec = computation(
        normalized,
        (returns,),
        Transformation.STANDARDIZE,
        normalization_state_id=state.fingerprint,
    )
    store.compute(normalized_spec, origin(181 * SECOND_NS), clocks(181 * SECOND_NS))
    return store, features


def main() -> None:
    with TemporaryDirectory(prefix="afre-feature-store-") as directory:
        path = Path(directory) / "features.sqlite"
        with FeatureStoreRepository(path) as repository:
            store, features = populate(repository)
            at = origin(181 * SECOND_NS)
            manifest = dataset(features)
            materialization = store.materialize((at,), manifest, features, 182 * SECOND_NS)
            before = canonical_json(materialization)
            close = next(
                item for item in features.definitions if item.definition.name == "market.close"
            )
            old = store.feature_as_of(close, at).selected
            assert old is not None
            revised = replace(
                old, clocks=clocks(360 * SECOND_NS), value=103.0, predecessor_id=old.fingerprint
            )
            with repository.transaction():
                store.append_vintage(revised)
            assert store.feature_as_of(close, at).selected == old
            assert store.feature_as_of(close, origin(361 * SECOND_NS)).selected == revised
            joined = store.point_in_time_join((at, origin(182 * SECOND_NS)), manifest, features)
            assert joined[0].row == materialization.results[0].row
            selected = joined[0].audits[0].selected
            assert selected is not None
            lineage_count = len(store.lineage(selected.fingerprint))
            audit_count = store.audit()
        with FeatureStoreRepository(path) as restarted:
            reloaded = restarted.get(type(materialization), materialization.fingerprint)
            assert canonical_json(reloaded) == before
            replay = FeatureStore(restarted).point_in_time_join((at,), manifest, features)
            assert canonical_json(replay[0]) == canonical_json(materialization.results[0])
        print("Future revision excluded; single/batch lookup parity verified")
        print("Supplied normalization fit cutoff: 122 seconds; state available: 123 seconds")
        print(
            f"Byte-identical restart replay; lineage nodes: {lineage_count}; "
            f"audited records: {audit_count}"
        )
        print(f"Materialization: {materialization.fingerprint}")


if __name__ == "__main__":
    main()
