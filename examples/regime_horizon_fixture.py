"""Independent actual one-hour and one-day targets with the same causal regime."""

from dataclasses import replace

from afre.feature_store.models import FeatureSetManifest
from afre.forecast import ForecastOrigin
from afre.ids import InstrumentId
from afre.multihorizon import (
    Architecture,
    HorizonModelBinding,
    HorizonSet,
    MultiHorizonEngine,
    MultiHorizonModelSpec,
    sharing_for,
)
from afre.regime_conditioned import (
    RegimeConditionedForecast,
    RegimeConditionedModel,
    RegimeConditioningSpec,
    RegimeEngine,
    RegimeRepository,
    RegimeScope,
    RegimeSubject,
)
from afre.research_datasets import (
    DatasetCompatibility,
    DatasetEngine,
    Partition,
    ResearchDatasetDefinition,
    ResearchOriginRequest,
    SplitDefinition,
    SplitStrategy,
)
from afre.research_datasets.samples import ResearchSample
from afre.statistical_models import ModelEngine, ModelFamily, PredictionScope
from afre.statistical_models.artifacts import DesignMatrix, FittedModelArtifact, ModelFitInputs
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.schema import (
    InterceptPolicy,
    NonconvergencePolicy,
    RankDeficiencyPolicy,
    SolverIdentity,
    TrainingMissingPolicy,
)
from afre.target_engine import TargetEngine, TargetSetManifest
from afre.target_engine.models import TargetDatasetManifest
from afre.time import TimeRange
from afre.universe import (
    ConstituentCoverage,
    EligibilityPolicy,
    IssuerRecord,
    ListingId,
    ListingRecord,
    SecurityRecord,
    StableIssuerId,
    StableSecurityId,
    TradabilityRecord,
    UniverseCalendar,
    UniverseDefinition,
    UniverseEngine,
    UniverseMembershipVintage,
    UniverseSession,
)
from afre.universe.schema import (
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
from examples.regime_conditioned_demo import snapshot, taxonomy
from examples.target_demo import CALENDAR_TARGET, SOURCE_MARKET, bar
from examples.target_demo import definition as target_definition
from examples.universe_demo import evidence

HOUR = 3_600_000_000_000
DAY = 24 * HOUR


def real_horizons(
    repo: RegimeRepository, heldout_scale: float = 1.0
) -> tuple[tuple[RegimeConditionedModel, tuple[RegimeConditionedForecast, ...]], ...]:
    feature = definition("market.real_horizon_value", lookback_ns=DAY)
    calendar = UniverseCalendar(
        CALENDAR,
        "real-hour-day-v1",
        "XTEST",
        "UTC",
        (UniverseSession("real-session", TimeRange(0, 1000 * DAY)),),
        evidence(InstrumentId("calendar", "real"), end=1000 * DAY),
    )
    universe = UniverseDefinition(
        "universe.real_horizons",
        "1",
        UniverseSourceKind.INDEX_MEMBERSHIP,
        SOURCE,
        EligibilityPolicy(),
        calendar,
    )
    target_calendar = replace(
        CALENDAR_TARGET,
        sessions=(replace(CALENDAR_TARGET.sessions[0], period=TimeRange(0, 1000 * DAY)),),
    )
    targets = TargetSetManifest(
        tuple(
            replace(target_definition(horizon_ns=h), name="target.real_" + name)
            for h, name in ((HOUR, "hour"), (DAY, "day"))
        )
    )
    securities = tuple(StableSecurityId("real-horizon", str(i)) for i in range(4))
    origins = (20 * DAY, 30 * DAY, 60 * DAY, 80 * DAY)
    with repo.transaction(), repo.validation_cache():
        for value in (
            SOURCE,
            feature,
            FeatureSetManifest((feature,)),
            calendar,
            SOURCE_MARKET,
            target_calendar,
            universe,
            *targets.definitions,
            targets,
        ):
            repo.put(value)
        for i, security in enumerate(securities):
            issuer = StableIssuerId("real-horizon-issuer", str(i))
            listing = ListingId("real-horizon-listing", str(i))
            ev = evidence(security.instrument, end=1000 * DAY)
            for value in (
                IssuerRecord(issuer, "US", evidence(issuer.instrument, end=1000 * DAY)),
                SecurityRecord(
                    security, issuer, SecurityType.COMMON_STOCK, "A", "equity", "USD", "US", ev
                ),
                ListingRecord(listing, security, "XTEST", "USD", True, CALENDAR, ev),
                TradabilityRecord(listing, security, TradabilityState.TRADABLE, ev),
                UniverseMembershipVintage(
                    universe.fingerprint, security, MembershipState.INCLUDED, ev
                ),
            ):
                repo.put(value)
            for at in origins:
                repo.put(
                    source_vintage(
                        feature, at, at, float(i + at // DAY), entity=security.instrument
                    )
                )
                for h, price in (
                    (0, 100.0 + i),
                    (HOUR, 102.0 + i + at / DAY / 100),
                    (DAY, 105.0 + i + at / DAY / 50),
                ):
                    repo.put(
                        replace(
                            bar(
                                at + h,
                                price * (heldout_scale if at >= 60 * DAY and h > 0 else 1.0),
                            ),
                            instrument=security.instrument,
                        )
                    )
        repo.put(
            ConstituentCoverage(
                universe.fingerprint,
                securities,
                SnapshotCompleteness.COMPLETE,
                evidence(InstrumentId("universe", "real"), end=1000 * DAY),
            )
        )
    ue, te = UniverseEngine(repo), TargetEngine(repo)
    requests = []
    for at in origins:
        us = ue.universe_as_of(universe, at, at)
        ue.persist_snapshot(us)
        manifest = to_universe_manifest(us)
        rows = tuple(
            ForecastOrigin(
                m.instrument, at, at, "synthetic-session-v1", BUILD, manifest.fingerprint
            )
            for m in manifest.memberships
        )
        source = te.freeze_source(SOURCE_MARKET, target_calendar, at + DAY)
        labels = te.build_dataset(
            "real-hour-day", rows, targets, source.fingerprint, manifest, clocks(at + DAY)
        )
        requests.append(
            ResearchOriginRequest(
                us.fingerprint, "synthetic-session-v1", BUILD, labels.fingerprint
            )
        )
    research = DatasetEngine(repo)
    compatibility = DatasetCompatibility(
        (INPUT_ID,),
        CALENDAR,
        (calendar.fingerprint,),
        (target_calendar.fingerprint,),
        feature.adjustment,
        (feature.adjustment.fingerprint,),
    )
    engine = RegimeEngine(repo)
    tax = taxonomy()
    engine.publish_taxonomy(tax)
    outputs, bindings = [], []
    for target in HorizonSet(targets.definitions).targets:
        definition_ = ResearchDatasetDefinition(
            "research.real_" + str(target.horizon.duration_ns),
            "1",
            FeatureSetManifest((feature,)),
            TargetSetManifest((target,)),
            compatibility,
        )
        horizon_requests = []
        for request in requests:
            old = repo.get(TargetDatasetManifest, request.target_dataset_id or "")
            endpoint = old.origins[0].timestamp_ns + (target.horizon.duration_ns or 0)
            source = te.freeze_source(SOURCE_MARKET, target_calendar, endpoint)
            labels = te.build_dataset(
                "real-single-horizon",
                old.origins,
                definition_.target_set,
                source.fingerprint,
                old.universe,
                clocks(endpoint),
            )
            horizon_requests.append(replace(request, target_dataset_id=labels.fingerprint))
        dataset = research.build_dataset(
            definition_, tuple(horizon_requests), 100 * DAY, 100 * DAY
        )
        split = research.build_split(
            dataset.fingerprint,
            SplitDefinition(
                "split.real_horizons",
                "1",
                SplitStrategy.FIXED_HOLDOUT,
                TimeRange(10 * DAY, 40 * DAY),
                TimeRange(50 * DAY, 70 * DAY),
                40 * DAY,
                test=TimeRange(75 * DAY, 90 * DAY),
            ),
        )
        spec = BaselineModelSpec(
            ModelFamily.UNCONDITIONAL_MEAN,
            definition_.feature_set,
            target,
            split.fold_ids[0],
            (),
            InterceptPolicy.GLOBAL,
            0.0,
            0.0,
            False,
            10000,
            1e-10,
            1e12,
            RankDeficiencyPolicy.FAIL,
            NonconvergencePolicy.FAIL,
            TrainingMissingPolicy.SKIP,
            0,
            SolverIdentity.REFERENCE_STATISTIC,
        )
        me = ModelEngine(repo)
        run = me.fit_model(spec, 40 * DAY, 40 * DAY, 40 * DAY)
        base = repo.get(FittedModelArtifact, run.artifact_id)
        matrix = repo.get(DesignMatrix, repo.get(ModelFitInputs, base.fit_inputs_id).matrix_id)
        rs = RegimeConditioningSpec(
            base.fingerprint, target, tax.fingerprint, RegimeScope.GLOBAL
        )
        subject = RegimeSubject(RegimeScope.GLOBAL, InstrumentId("regime", "real-global"))
        observations = []
        for row in matrix.rows:
            sample = repo.get(ResearchSample, row.sample_id)
            sid = engine.publish_snapshot(snapshot(tax, sample, state="A", subject=subject))
            observations.append(engine.observe(rs, sample.fingerprint, (sid,)))
        model = engine.fit(
            rs, tuple(o.fingerprint for o in observations), 40 * DAY, 40 * DAY, 40 * DAY
        )
        points = me.predict_samples(
            base.fingerprint,
            tuple(
                s.fingerprint
                for s in research.partition_samples(split.fold_ids[0], Partition.VALIDATION)
            ),
            PredictionScope.VALIDATION,
        )
        forecasts = []
        for point in points:
            sample = repo.get(ResearchSample, point.input.sample_id or "")
            sid = engine.publish_snapshot(snapshot(tax, sample, state="A", subject=subject))
            observation = engine.observe(rs, sample.fingerprint, (sid,))
            forecasts.append(
                engine.forecast(
                    model.fingerprint,
                    observation.fingerprint,
                    point.fingerprint,
                    sample.timestamp_ns,
                )
            )
        outputs.append((model, tuple(forecasts)))
        bindings.append(
            HorizonModelBinding(
                target.fingerprint,
                definition_.feature_set.fingerprint,
                spec.fingerprint,
                base.fingerprint,
                split.fold_ids[0],
                40 * DAY,
                (),
            )
        )
    horizons = HorizonSet(targets.definitions)
    mh = MultiHorizonModelSpec(
        horizons,
        Architecture.INDEPENDENT_PER_HORIZON,
        tuple(bindings),
        sharing_for(horizons, Architecture.INDEPENDENT_PER_HORIZON),
        (1.0, 1.0),
    )
    MultiHorizonEngine(repo).fit(mh, 40 * DAY, 40 * DAY, 40 * DAY)
    assert outputs[0][0].fingerprint != outputs[1][0].fingerprint
    assert outputs[0][1][0].regime_snapshot_id == outputs[1][1][0].regime_snapshot_id
    return tuple(outputs)
