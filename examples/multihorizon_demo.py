"""Offline exact 5/15 elapsed horizons, independent calibration and shared TRAIN fit."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.calibration import (
    CalibrationEngine,
    CalibrationMethod,
    CalibrationPartition,
    CalibrationPartitionPolicy,
    CalibrationRequest,
    CalibrationSpec,
)
from afre.multihorizon import (
    Architecture,
    ComponentState,
    HorizonForecastEntry,
    HorizonModelBinding,
    HorizonSet,
    MultiHorizonEngine,
    MultiHorizonFitRun,
    MultiHorizonForecast,
    MultiHorizonModelSpec,
    MultiHorizonRepository,
    sharing_for,
    surfaces,
)
from afre.probabilistic import (
    DistributionFamily,
    ObservationPolicy,
    ProbabilisticEngine,
    ProbabilisticForecast,
)
from afre.research_datasets import DatasetEngine, Partition, SplitStrategy
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.splits import EmbargoPolicy
from afre.serialization import canonical_json
from afre.statistical_models import ModelEngine, ModelFamily, PredictionScope
from afre.statistical_models.artifacts import ModelFitInputs, PointForecast
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
from examples.feature_store_demo import clocks
from examples.probabilistic_demo import probability_spec
from examples.research_dataset_demo import populate, split_definition
from examples.target_demo import CALENDAR_TARGET, SOURCE_MARKET


@dataclass(frozen=True)
class MultiHorizonFixture:
    spec: MultiHorizonModelSpec
    run: MultiHorizonFitRun
    deployment: tuple[tuple[ProbabilisticForecast, ...], ...]
    tests: tuple[tuple[ProbabilisticForecast, ...], ...]
    bundles: tuple[MultiHorizonForecast, ...]


def build_fixture(
    repo: MultiHorizonRepository,
    reverse: bool = False,
    heldout_scale: float = 40.0,
    feature_specific: bool = False,
) -> MultiHorizonFixture:
    f = populate(
        repo, reverse=reverse, missing=False, security_count=5, validation_outlier=heldout_scale
    )
    horizons = HorizonSet(f.definition.target_set.definitions)
    target_engine, research = TargetEngine(repo), DatasetEngine(repo)
    bindings, deployment, tests, calibrated = [], [], [], []
    for h, target in enumerate(horizons.targets):
        requests = []
        for request in f.requests:
            old = repo.get(TargetDatasetManifest, request.target_dataset_id or "")
            at = old.origins[0].timestamp_ns + (target.horizon.duration_ns or 0)
            source = target_engine.freeze_source(SOURCE_MARKET, CALENDAR_TARGET, at)
            labels = target_engine.build_dataset(
                "multi-horizon-truth",
                old.origins,
                TargetSetManifest((target,)),
                source.fingerprint,
                old.universe,
                clocks(at),
            )
            requests.append(replace(request, target_dataset_id=labels.fingerprint))
        definition = replace(
            f.definition, name=f"research.horizon_{h}", target_set=TargetSetManifest((target,))
        )
        if feature_specific and h == 1:
            from afre.feature_store.models import FeatureSetManifest
            from examples.feature_store_demo import definition as feature_definition
            from examples.feature_store_demo import source_vintage

            alternate = feature_definition("market.slow_value", lookback_ns=4)
            with repo.transaction():
                repo.put(alternate)
                repo.put(FeatureSetManifest((alternate,)))
                for old_request in requests:
                    old = repo.get(TargetDatasetManifest, old_request.target_dataset_id or "")
                    for origin in old.origins:
                        repo.put(
                            source_vintage(
                                alternate,
                                origin.timestamp_ns,
                                origin.timestamp_ns,
                                float(origin.timestamp_ns),
                                entity=origin.instrument,
                            )
                        )
            definition = replace(definition, feature_set=FeatureSetManifest((alternate,)))
        dataset = research.build_dataset(
            definition, tuple(reversed(requests)) if reverse else tuple(requests), 100, 100
        )
        split = research.build_split(
            dataset.fingerprint,
            replace(
                split_definition(f),
                strategy=SplitStrategy.FIXED_HOLDOUT,
                step_ns=0,
                fold_count=1,
                validation=TimeRange(40, 70),
                test=TimeRange(80, 90),
                embargo=EmbargoPolicy(),
                preprocessing_spec_ids=(),
            ),
        )
        base = BaselineModelSpec(
            ModelFamily.UNCONDITIONAL_MEAN,
            definition.feature_set,
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
        point = ModelEngine(repo).fit_model(base, 40, 40, 40)
        raw_spec = replace(
            probability_spec(
                point.artifact_id,
                split.fold_ids[0],
                f,
                DistributionFamily.EMPIRICAL_RESIDUAL,
                ObservationPolicy.POINT_MODEL_RESIDUALS,
            ),
            target=target,
        )
        probability = ProbabilisticEngine(repo)
        raw_run = probability.fit_model(raw_spec, 40, 40, 40)
        with repo.read_snapshot(), repo.validation_cache():
            validation = repo.partition_samples(split.fold_ids[0], Partition.VALIDATION)
            test_samples = repo.partition_samples(split.fold_ids[0], Partition.TEST)
        raw = probability.predict_samples(
            raw_run.artifact_id,
            tuple(s.fingerprint for s in validation),
            PredictionScope.VALIDATION,
        )
        reservation = tuple(p for p in raw if p.input.origin.timestamp_ns == 40)
        deployed = tuple(p for p in raw if p.input.origin.timestamp_ns == 60)
        test = probability.predict_samples(
            raw_run.artifact_id,
            tuple(s.fingerprint for s in test_samples),
            PredictionScope.TEST,
        )
        cs = CalibrationSpec(
            raw_run.artifact_id,
            raw_spec.fingerprint,
            target,
            CalibrationMethod.IDENTITY,
            CalibrationPartition(
                CalibrationPartitionPolicy.DEDICATED_CALIBRATION,
                split.fold_ids[0],
                tuple(p.input.sample_id or "" for p in reservation),
                TimeRange(40, 50),
            ),
            55,
            2,
            raw_spec.thresholds,
            raw_spec.quantiles,
        )
        cal = CalibrationEngine(repo)
        cr = cal.fit(
            cs,
            tuple(
                CalibrationRequest(
                    p.fingerprint,
                    repo.get(ResearchSample, p.input.sample_id or "").target_id or "",
                )
                for p in reservation
            ),
            55,
            55,
            55,
        )
        adjusted = cal.apply_batch(cr.state_id, tuple(p.fingerprint for p in deployed))
        inputs = repo.get(ModelFitInputs, point.inputs.fingerprint)
        bindings.append(
            HorizonModelBinding(
                target.fingerprint,
                definition.feature_set.fingerprint,
                base.fingerprint,
                point.artifact_id,
                base.fold_id,
                inputs.training_cutoff_ns,
                (),
                raw_spec.fingerprint,
                raw_run.artifact_id,
                cs.fingerprint,
                cr.state_id,
            )
        )
        deployment.append(deployed)
        tests.append(test)
        calibrated.append(adjusted)
    spec = MultiHorizonModelSpec(
        horizons,
        Architecture.INDEPENDENT_PER_HORIZON,
        tuple(bindings),
        sharing_for(horizons, Architecture.INDEPENDENT_PER_HORIZON),
        (1.0, 2.0),
    )
    engine = MultiHorizonEngine(repo)
    run = engine.fit(spec, 55, 55, 55)
    maps = [{p.input.origin.fingerprint: p for p in ps} for ps in deployment]
    cal_maps = [{p.input.origin.fingerprint: p for p in ps} for ps in calibrated]
    bundles = []
    for key in sorted(set(maps[0]).intersection(*(set(m) for m in maps[1:]))):
        forecasts = tuple(m[key] for m in maps)
        entries = tuple(
            HorizonForecastEntry(
                p.target_definition_id,
                ComponentState.AVAILABLE,
                p.point_forecast_id,
                p.fingerprint,
                m[key].fingerprint,
            )
            for p, m in zip(forecasts, cal_maps, strict=True)
        )
        bundles.append(
            engine.build_bundle(run.fingerprint, forecasts[0].input.origin, entries, 60)
        )
    return MultiHorizonFixture(spec, run, tuple(deployment), tuple(tests), tuple(bundles))


def backbone_spec(f: MultiHorizonFixture) -> MultiHorizonModelSpec:
    architecture = Architecture.SHARED_LINEAR_BACKBONE
    bindings = tuple(
        replace(
            b,
            probability_spec_id=None,
            probability_model_id=None,
            calibration_spec_id=None,
            calibration_state_id=None,
        )
        for b in f.spec.bindings
    )
    return replace(
        f.spec,
        architecture=architecture,
        bindings=bindings,
        sharing=sharing_for(f.spec.horizon_set, architecture),
        shared_cutoff_ns=40,
        ridge_penalty=1e-6,
    )


def main() -> None:
    with TemporaryDirectory(prefix="afre-multihorizon-demo-") as directory:
        path = Path(directory) / "research.sqlite"
        with MultiHorizonRepository(path) as repo:
            fixture = build_fixture(repo)
            engine = MultiHorizonEngine(repo)
            covariance = engine.fit_dependence(fixture.run.fingerprint, 40, 55)
            bundle = fixture.bundles[0]
            joint = engine.build_bundle(
                fixture.run.fingerprint,
                bundle.origin,
                bundle.entries,
                60,
                covariance.fingerprint,
            )
            expectation, median, surface = surfaces(repo, joint)
            assert len(expectation) == len(median) == len(surface) == 2
            evaluation = engine.evaluate(tuple(b.fingerprint for b in fixture.bundles), 75, 75)
            consistency = engine.consistency_audit(joint.fingerprint)
            shared = engine.fit(backbone_spec(fixture), 55, 55, 55)
            outputs = tuple(
                engine.predict_shared(shared.fingerprint, e.point_forecast_id or "", 60)
                for e in bundle.entries
            )
            shared_bundle = engine.build_bundle(
                shared.fingerprint,
                bundle.origin,
                tuple(
                    HorizonForecastEntry(
                        p.target_definition_id, ComponentState.AVAILABLE, p.fingerprint
                    )
                    for p in outputs
                ),
                60,
            )
            audit = engine.lineage_audit(joint.fingerprint)
            ids = (
                joint.fingerprint,
                shared_bundle.fingerprint,
                evaluation.fingerprint,
                audit.fingerprint,
            )
            frozen = tuple(canonical_json(repo.get_any(i)) for i in ids)
            from examples.calibration_demo import corrected_calibration_truth

            raw = fixture.deployment[1][0]
            sample = repo.get(ResearchSample, raw.input.sample_id or "")
            corrected_calibration_truth(repo, sample.target_id or "", 110, 10.0)
            assert engine.fit_dependence(fixture.run.fingerprint, 40, 55) == covariance
            # New calibration evidence can serve a later origin, never the old origin60.
            from afre.calibration import CalibrationObservationSet, CalibrationState
            from afre.feature_store.engine import FeatureStore
            from afre.feature_store.materialization import PointInTimeJoinResult
            from afre.statistical_models.artifacts import PredictionInput
            from afre.universe import UniverseEngine, to_universe_manifest
            from afre.universe.models import UniverseSnapshot
            from examples.feature_store_demo import source_vintage

            long_binding = fixture.spec.bindings[1]
            long_state = repo.get(CalibrationState, long_binding.calibration_state_id or "")
            observations = repo.get(
                CalibrationObservationSet, long_state.inputs.observations_id
            )
            cs = replace(
                repo.get(CalibrationSpec, long_binding.calibration_spec_id or ""),
                method=CalibrationMethod.BINNED_PROBABILITY,
            )
            calibration = CalibrationEngine(repo)
            before_state = calibration.fit(cs, observations.requests, 55, 55, 55)
            first_request = observations.requests[0]
            corrected_id = corrected_calibration_truth(repo, first_request.target_id, 110, 0.1)
            corrected_requests = tuple(
                replace(r, target_id=corrected_id) if r == first_request else r
                for r in observations.requests
            )
            updated_spec = replace(cs, cutoff_ns=110)
            after_state = calibration.fit(updated_spec, corrected_requests, 110, 110, 110)
            assert before_state.state_id != after_state.state_id
            old_snapshot = repo.get(UniverseSnapshot, sample.snapshot_id)
            universe_engine = UniverseEngine(repo)
            snapshot = universe_engine.universe_as_of(old_snapshot.definition, 120, 120)
            universe_engine.persist_snapshot(snapshot)
            universe = to_universe_manifest(snapshot)
            origin = replace(
                bundle.origin,
                timestamp_ns=120,
                availability_cutoff_ns=120,
                universe_id=universe.fingerprint,
            )
            point = repo.get(PointForecast, bundle.entries[0].point_forecast_id or "")
            old_join = repo.get(PointInTimeJoinResult, point.input.join_id)
            base = repo.get(BaselineModelSpec, fixture.spec.bindings[0].point_spec_id)
            with repo.transaction():
                for feature in base.feature_set.definitions:
                    repo.put(source_vintage(feature, 120, 120, 42.0, entity=origin.instrument))
            manifest = replace(
                old_join.row.dataset, origins=TimeRange(120, 121), universe=universe
            )
            joined = FeatureStore(repo).materialize((origin,), manifest, base.feature_set, 120)
            with repo.transaction():
                repo.put(universe)
                repo.put(manifest)
                for audit_row in joined.results[0].audits:
                    repo.put(audit_row)
                repo.put(joined.results[0])
            request = PredictionInput(
                origin, joined.results[0].fingerprint, None, PredictionScope.OUT_OF_SAMPLE_OTHER
            )
            raws = tuple(
                ProbabilisticEngine(repo).predict(b.probability_model_id or "", request, 120)
                for b in fixture.spec.bindings
            )
            later_bundles = []
            for state_run, cal_spec, fit_at in (
                (before_state, cs, 55),
                (after_state, updated_spec, 110),
            ):
                spec = replace(
                    fixture.spec,
                    bindings=(
                        fixture.spec.bindings[0],
                        replace(
                            long_binding,
                            calibration_spec_id=cal_spec.fingerprint,
                            calibration_state_id=state_run.state_id,
                        ),
                    ),
                )
                fit = engine.fit(spec, fit_at, fit_at, fit_at)
                states = (
                    fixture.spec.bindings[0].calibration_state_id or "",
                    state_run.state_id,
                )
                adjusted = tuple(
                    calibration.apply(state_id, raw.fingerprint, 120)
                    for state_id, raw in zip(states, raws, strict=True)
                )
                entries = tuple(
                    HorizonForecastEntry(
                        raw.target_definition_id,
                        ComponentState.AVAILABLE,
                        raw.point_forecast_id,
                        raw.fingerprint,
                        cal.fingerprint,
                    )
                    for raw, cal in zip(raws, adjusted, strict=True)
                )
                later_bundles.append(engine.build_bundle(fit.fingerprint, origin, entries, 120))
            assert later_bundles[0].fingerprint != later_bundles[1].fingerprint
            assert (
                surfaces(repo, later_bundles[0], True)[2][1].probabilities
                != surfaces(repo, later_bundles[1], True)[2][1].probabilities
            )
            engine.lineage_audit(later_bundles[1].fingerprint)
            assert tuple(canonical_json(repo.get_any(i)) for i in ids) == frozen
            print(
                "horizons",
                [h.duration_ns for h in fixture.spec.horizon_set.horizons],
                "intersection",
                len(shared.intersection),
                "covariance",
                covariance.matrix,
                "weighted MSE",
                evaluation.weighted_mse,
                "consistency",
                consistency.checks,
                "lineage",
                len(audit.evidence_ids),
            )
        with MultiHorizonRepository(path) as restarted:
            assert tuple(canonical_json(restarted.get_any(i)) for i in ids) == frozen
            restarted.audit()
        print(
            "PASS: causal horizon-specific truth/calibration, matched TRAIN covariance, "
            "explicit shared fit, separate surfaces/evaluation and byte-identical replay"
        )


if __name__ == "__main__":
    main()
