"""Causal synthetic sources and eligible unpenalized native/nonlinear/sequence readouts."""

from dataclasses import dataclass, replace

from afre.calibration.artifacts import CalibratedForecast
from afre.event_conditioned.artifacts import EventConditionedForecast
from afre.mixture.artifacts import MixtureForecast
from afre.nonlinear import InteractionSet, NonlinearEngine, NonlinearInput
from afre.nonlinear.artifacts import NonlinearForecast
from afre.probabilistic import DistributionFamily, ObservationPolicy, ProbabilisticEngine
from afre.probabilistic.artifacts import ProbabilisticForecast, ProbabilisticModelArtifact
from afre.probabilistic.definitions import ProbabilisticModelSpec
from afre.regime_conditioned.artifacts import RegimeConditionedForecast
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import Artifact
from afre.sequence import SequenceEngine, SequenceForecast
from afre.statistical_models import ModelEngine, ModelFamily, PredictionScope
from afre.statistical_models.artifacts import FittedModelArtifact, PointForecast
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.schema import SolverIdentity
from afre.uncertainty import (
    ClosurePolicy,
    CovarianceAssumption,
    ParameterCovariance,
    ParameterUncertaintySpec,
    UncertaintyEngine,
    UncertaintyMeasure,
    UncertaintyRepository,
    UncertaintyRequest,
    UncertaintySpec,
    UncertaintyType,
)
from examples.regime_conditioned_demo import build_fixture as regime_fixture
from examples.sequence_demo import SequenceFixture
from examples.sequence_demo import build_fixture as sequence_fixture


@dataclass(frozen=True)
class UncertaintyFixture:
    upstream: SequenceFixture
    sources: tuple[tuple[str, tuple[str, ...]], ...]
    covariances: tuple[ParameterCovariance, ...]
    decompositions: tuple[tuple[str, tuple[str, ...]], ...]
    test_ids: tuple[str, ...]

    def ids(self, name: str) -> tuple[str, ...]:
        return dict(self.sources)[name]

    def results(self, name: str) -> tuple[str, ...]:
        return dict(self.decompositions)[name]


def requests(exact: bool = False) -> tuple[UncertaintyRequest, ...]:
    return tuple(
        UncertaintyRequest(
            k,
            UncertaintyMeasure.ENTROPY
            if k is UncertaintyType.REGIME_AMBIGUITY
            else UncertaintyMeasure.DISAGREEMENT
            if k is UncertaintyType.EVENT_AMBIGUITY
            else UncertaintyMeasure.QUALITY_PENALTY
            if k is UncertaintyType.DATA_QUALITY
            else UncertaintyMeasure.VARIANCE,
        )
        for k in UncertaintyType
        if not exact or k is not UncertaintyType.RESIDUAL_UNATTRIBUTED
    )


def stored_forecasts(
    repo: UncertaintyRepository, table: str, name: str
) -> tuple[Artifact, ...]:
    # Caller-fixed AFRE table/family names; no external path or executable provider input.
    return tuple(
        repo.get_any(row[0])
        for row in repo._connection.execute(
            f"SELECT fingerprint FROM {table} WHERE type_name=? ORDER BY fingerprint", (name,)
        )
    )


def build_fixture(
    repo: UncertaintyRepository, reverse: bool = False, upstream: SequenceFixture | None = None
) -> UncertaintyFixture:
    upstream = upstream or sequence_fixture(repo, reverse)
    sequence_source = repo.get(SequenceForecast, upstream.forecasts[0][0])
    assert sequence_source.probability is not None
    native_raw = repo.get(ProbabilisticForecast, sequence_source.probability.base_forecast_id)
    native = repo.get(
        FittedModelArtifact,
        repo.get(PointForecast, native_raw.point_forecast_id).model_artifact_id,
    )
    base_spec = repo.get(BaselineModelSpec, native.spec_id)
    model_engine, probability, engine = (
        ModelEngine(repo),
        ProbabilisticEngine(repo),
        UncertaintyEngine(repo),
    )
    linear_spec = replace(
        base_spec,
        family=ModelFamily.LINEAR_REGRESSION,
        solver=SolverIdentity.PIVOTED_HOUSEHOLDER_QR,
    )
    linear = model_engine.model_artifact(
        model_engine.fit_model(linear_spec, 40, 40, 40).artifact_id
    )
    points = model_engine.predict_samples(
        linear.fingerprint,
        tuple(
            s.fingerprint
            for s in repo.partition_samples(linear_spec.fold_id, Partition.VALIDATION)
        ),
        PredictionScope.VALIDATION,
    )
    test_points = model_engine.predict_samples(
        linear.fingerprint,
        tuple(
            s.fingerprint for s in repo.partition_samples(linear_spec.fold_id, Partition.TEST)
        ),
        PredictionScope.TEST,
    )
    old_probability_spec = repo.get(
        ProbabilisticModelSpec,
        repo.get(ProbabilisticModelArtifact, native_raw.model_artifact_id).spec_id,
    )
    raw_sets = []
    for family in (
        DistributionFamily.GAUSSIAN_LOCATION_SCALE,
        DistributionFamily.EMPIRICAL_RESIDUAL,
    ):
        p_spec = replace(
            old_probability_spec,
            point_model_id=linear.fingerprint,
            family=family,
            observation_policy=ObservationPolicy.POINT_MODEL_RESIDUALS,
        )
        run = probability.fit_model(p_spec, 40, 40, 40)
        raw_sets.append(
            probability.predict_batch(
                run.artifact_id, tuple(p.input for p in (*points, *test_points))
            )
        )
    gaussian, empirical = raw_sets
    gaussian_by_sample = {p.input.sample_id: p for p in gaussian}
    nl = NonlinearEngine(repo)
    interaction = next(
        d
        for d in upstream.upstream.specs[0].interaction_set.definitions
        if d.interaction_id == "micro-context"
    )
    nl_spec = replace(
        upstream.upstream.specs[0],
        interaction_set=InteractionSet((interaction,), base_spec.target),
        ridge_penalty=0.0,
    )

    def restricted_input(identity: str) -> str:
        packet = repo.get(NonlinearInput, identity)
        return nl.input(
            packet.sample_id,
            tuple(s.fingerprint for s in packet.scalars if s.definition in nl_spec.features),
        ).fingerprint

    matrix = nl.matrix(
        nl_spec, tuple(restricted_input(i) for i in upstream.upstream.train_ids), (), 40
    )
    nl_model = nl.fit(nl_spec, matrix.fingerprint, 40, 40, 40)
    nonlinear_forecasts = []
    for identity in (*upstream.upstream.validation_ids, *upstream.upstream.test_ids):
        packet = repo.get(NonlinearInput, identity)
        raw = gaussian_by_sample[packet.sample_id]
        nonlinear_forecasts.append(
            nl.predict(
                nl_model.fingerprint,
                restricted_input(identity),
                packet.origin.timestamp_ns,
                raw.fingerprint,
            )
        )
    sequence = SequenceEngine(repo)
    seq_spec = replace(upstream.specs[0], features=(upstream.features[0],), ridge_penalty=0.0)
    bindings = []
    for sample_id, _ in upstream.bindings:
        sample = repo.get(ResearchSample, sample_id)
        assert sample.origin is not None
        snap = sequence.snapshot(sample.origin, seq_spec.features, seq_spec.window, 40)
        bindings.append((sample_id, snap.fingerprint))
    state = sequence.fit_transform(seq_spec, tuple(bindings), 40, 40, 40)
    data = sequence.dataset(seq_spec, state.fingerprint, 40)
    seq_model = sequence.fit(seq_spec, data.fingerprint, 40, 40, 40)
    sequence_forecasts = []
    for sample_id, _ in (*upstream.validation, *upstream.test):
        sample = repo.get(ResearchSample, sample_id)
        assert sample.origin is not None
        snap = sequence.snapshot(
            sample.origin, seq_spec.features, seq_spec.window, sample.timestamp_ns
        )
        sequence_forecasts.append(
            sequence.predict(
                seq_model.fingerprint,
                sample_id,
                snap.fingerprint,
                sample.timestamp_ns,
                gaussian_by_sample[sample_id].fingerprint,
            )
        )
    covariance = tuple(
        engine.fit_covariance(
            ParameterUncertaintySpec(
                m.fingerprint, CovarianceAssumption.IID_HOMOSKEDASTIC_CORRECT_LINEAR
            ),
            40,
        )
        for m in (linear, nl_model, seq_model)
    )
    soft = regime_fixture(
        repo, reverse=reverse, upstream=upstream.upstream.upstream.upstream.upstream, soft=True
    )
    target = base_spec.target

    def at_sixty(value: Artifact) -> bool:
        assert isinstance(
            value,
            (
                ProbabilisticForecast,
                CalibratedForecast,
                PointForecast,
                EventConditionedForecast,
                RegimeConditionedForecast,
                MixtureForecast,
                NonlinearForecast,
                SequenceForecast,
            ),
        )
        origin = (
            value.input.origin
            if isinstance(value, (ProbabilisticForecast, CalibratedForecast, PointForecast))
            else value.origin
        )
        return origin.timestamp_ns == 60 and value.target_definition_id == target.fingerprint

    sources = {
        "gaussian": tuple(p.fingerprint for p in gaussian if at_sixty(p)),
        "empirical": tuple(p.fingerprint for p in empirical if at_sixty(p)),
        "point": tuple(p.fingerprint for p in points if at_sixty(p)),
        "mixture": tuple(
            i
            for i in upstream.upstream.upstream.probability_ids
            if at_sixty(repo.get(MixtureForecast, i))
        ),
        "event": tuple(
            p.fingerprint
            for p in stored_forecasts(repo, "ec_artifacts", "EventConditionedForecast")
            if at_sixty(p)
        ),
        "hard-regime": tuple(i for i in upstream.upstream.upstream.upstream.forecast_ids),
        "soft-regime": soft.forecast_ids,
        "nonlinear": tuple(p.fingerprint for p in nonlinear_forecasts if at_sixty(p)),
        "tree": upstream.upstream.forecast_ids[-1],
        "sequence": tuple(p.fingerprint for p in sequence_forecasts if at_sixty(p)),
        "calibrated": tuple(
            p.fingerprint
            for p in stored_forecasts(repo, "c_artifacts", "CalibratedForecast")
            if at_sixty(p)
        ),
    }
    # Keep one declared event model per exact sample in this bounded fixture.
    from afre.uncertainty.sources import source_for

    for name, ids in sources.items():
        unique = {source_for(repo, i).sample_id: i for i in sorted(ids)}
        sources[name] = tuple(sorted(unique.values()))
    decompositions = []
    for name, ids in sorted(sources.items()):
        results = []
        estimator = (
            covariance[0]
            if name in ("gaussian", "empirical", "point")
            else covariance[1]
            if name == "nonlinear"
            else covariance[2]
            if name == "sequence"
            else None
        )
        for identity in reversed(ids) if reverse else ids:
            spec = UncertaintySpec(
                target,
                identity,
                tuple(reversed(requests(name == "mixture")))
                if reverse
                else requests(name == "mixture"),
                closure=ClosurePolicy.EXACT_ADDITIVE
                if name == "mixture"
                else ClosurePolicy.NON_ADDITIVE_DIAGNOSTICS_ONLY,
                covariance_id=estimator.fingerprint if estimator else None,
                interval_levels=(0.1, 0.9),
            )
            source = source_for(repo, identity)
            results.append(engine.decompose(spec, source.origin.timestamp_ns).fingerprint)
        decompositions.append((name, tuple(sorted(results))))
    test_results = []
    for raw in gaussian:
        if raw.input.scope is PredictionScope.TEST:
            spec = UncertaintySpec(
                target,
                raw.fingerprint,
                requests(),
                covariance_id=covariance[0].fingerprint,
                interval_levels=(0.1, 0.9),
            )
            test_results.append(
                engine.decompose(spec, raw.input.origin.timestamp_ns).fingerprint
            )
    return UncertaintyFixture(
        upstream,
        tuple(sorted(sources.items())),
        covariance,
        tuple(decompositions),
        tuple(sorted(test_results)),
    )
