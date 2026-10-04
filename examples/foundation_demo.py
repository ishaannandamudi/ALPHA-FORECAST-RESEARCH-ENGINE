"""Deterministic foundation walkthrough with synthetic data and no fitted model."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.datasets import (
    AdjustmentBasis,
    AdjustmentPolicy,
    DatasetManifest,
    ForecastFeatureRow,
    UniverseManifest,
    UniverseMembership,
    UniversePolicy,
)
from afre.evaluation import CostPolicy, EvaluationPolicy, SplitPolicy
from afre.experiments import ExperimentSpec
from afre.features import (
    AvailabilityRule,
    DataQuality,
    FeatureDefinition,
    FeatureScope,
    FeatureSemantic,
    FeatureSet,
    FeatureValue,
    MissingPolicy,
    MissingState,
    ValueType,
)
from afre.forecast import ForecastOrigin
from afre.hashing import bytes_digest
from afre.horizons import ForecastHorizon, HorizonBasis
from afre.ids import InstrumentId
from afre.lineage import FeatureLineage, Parameter, ProvenanceRef
from afre.models import ModelSpec, TrainingPolicy
from afre.persistence import ArtifactStore
from afre.schema import ContractError
from afre.targets import ForecastTargetRow, TargetSpec, TargetType
from afre.time import DAY_NS, TimeRange
from afre.validation import validate_training_pair


@dataclass(frozen=True)
class Demo:
    instrument: InstrumentId
    origin: ForecastOrigin
    features: tuple[FeatureValue, ...]
    row: ForecastFeatureRow
    target: ForecastTargetRow
    experiment: ExperimentSpec


def build_demo() -> Demo:
    security = InstrumentId("synthetic-security", "0001")
    universe = UniverseManifest(
        "historical-demo",
        "synthetic-membership-v1",
        "eligibility-v1",
        UniversePolicy.POINT_IN_TIME,
        (UniverseMembership(security, TimeRange(0, 50 * DAY_NS), 0, "synthetic"),),
    )
    origin = ForecastOrigin(
        security,
        10 * DAY_NS,
        10 * DAY_NS,
        "synthetic-session-v1",
        "demo-build-v1",
        universe.fingerprint,
    )
    definitions = tuple(
        FeatureDefinition(
            name,
            "1",
            FeatureSemantic.MARKET,
            ValueType.NUMBER,
            "ratio",
            FeatureScope.INSTRUMENT,
            DAY_NS,
            AvailabilityRule.SOURCE_PUBLICATION,
            MissingPolicy.EXPLICIT_STATE,
            "identity-v1",
        )
        for name in ("lagged_return", "lagged_range")
    )
    source = ProvenanceRef("synthetic", "market-v1", "1", bytes_digest(b"demo-market-v1"))
    lineage = FeatureLineage((source,), (), "identity-v1", (), "demo-build-v1", "demo-code-v1")
    values = tuple(
        FeatureValue(
            definition,
            security,
            9 * DAY_NS,
            9 * DAY_NS,
            origin.timestamp_ns,
            value,
            MissingState.PRESENT,
            "synthetic",
            "1",
            DataQuality.VERIFIED,
            lineage,
        )
        for definition, value in zip(definitions, (0.01, 0.02), strict=True)
    )
    target_spec = TargetSpec(
        TargetType.SIMPLE_RETURN,
        ForecastHorizon(HorizonBasis.ELAPSED_TIME, duration_ns=DAY_NS),
        "ratio",
        "label-contract-v1",
    )
    dataset = DatasetManifest(
        "demo-dataset",
        TimeRange(0, 40 * DAY_NS),
        universe,
        FeatureSet(definitions),
        (target_spec,),
        (source.fingerprint,),
        "synthetic-calendar-v1",
        AdjustmentPolicy(AdjustmentBasis.RAW, 0),
        MissingPolicy.EXPLICIT_STATE,
        "demo-build-v1",
    )
    row = ForecastFeatureRow(origin, dataset, values)
    target = ForecastTargetRow(
        origin,
        target_spec,
        TimeRange(10 * DAY_NS, 11 * DAY_NS),
        0.015,
        11 * DAY_NS + 1,
        source.fingerprint,
        DataQuality.VERIFIED,
    )
    model = ModelSpec(
        "metadata-only-baseline",
        (Parameter("intercept", True),),
        dataset.feature_set,
        target_spec,
        TrainingPolicy("expanding", "1", ()),
        42,
        "unimplemented-baseline-v1",
    )
    split = SplitPolicy(
        TimeRange(DAY_NS, 15 * DAY_NS),
        TimeRange(16 * DAY_NS, 20 * DAY_NS),
        TimeRange(22 * DAY_NS, 25 * DAY_NS),
        15 * DAY_NS,
        27 * DAY_NS,
        True,
        DAY_NS // 2,
        "purged-walk-forward-contract-v1",
    )
    experiment = ExperimentSpec(
        "demo-experiment",
        dataset,
        model,
        split,
        EvaluationPolicy("distribution-scores", "1", ("crps",)),
        CostPolicy("declared-research-frictions", "1", (Parameter("spread_bps", 2.0),)),
        42,
        "demo-code-v1",
    )
    return Demo(security, origin, values, row, target, experiment)


def main() -> None:
    demo = build_demo()
    future = replace(demo.features[0], available_ns=demo.origin.timestamp_ns + 1)
    try:
        replace(demo.row, features=(future, demo.features[1]))
    except ContractError as error:
        print(f"Future feature rejected: {error}")
    else:
        raise AssertionError("future feature was accepted")
    assert not demo.target.eligible_at(demo.origin.timestamp_ns)
    validate_training_pair(demo.row, demo.target, demo.experiment.split.training_cutoff_ns)
    artifacts = (
        demo.experiment.dataset.universe,
        *demo.experiment.dataset.feature_set.definitions,
        demo.experiment.dataset,
        demo.experiment.model,
        demo.experiment,
    )
    before = tuple(item.fingerprint for item in artifacts)
    with TemporaryDirectory(prefix="afre-demo-") as directory:
        path = Path(directory) / "research.sqlite"
        with ArtifactStore(path) as store, store.transaction():
            for artifact in artifacts:
                store.put(artifact)
        with ArtifactStore(path) as restarted:
            after = tuple(
                restarted.get(type(item), item.fingerprint).fingerprint for item in artifacts
            )
            assert before == after
            assert restarted.audit() == len(artifacts)
    print("Restart replay: all six artifact fingerprints unchanged")
    print(f"Experiment identity: {demo.experiment.fingerprint}")


if __name__ == "__main__":
    main()
