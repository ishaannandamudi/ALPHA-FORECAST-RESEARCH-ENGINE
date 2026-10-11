"""Offline native sources and exact research context shared by tests, demo and profile."""

from dataclasses import dataclass, replace

from afre.challenger import (
    ChallengeDirection,
    ChallengeEngine,
    ChallengeMetric,
    ChallengeMetricRequest,
    ChallengeProgram,
    ChallengeTestPolicy,
    ChallengeWindow,
    EvaluationEvidence,
    ParticipantRole,
    PromotionCriterion,
)
from afre.cross_sectional import (
    CrossSectionEngine,
    CrossSectionIdentity,
    CrossSectionSpec,
    ScoreSource,
    ScoreSpec,
)
from afre.fusion import FusionKind
from afre.health import HealthDiagnostic
from afre.orthogonalization import OrthogonalizationEngine
from afre.probabilistic import ProbabilisticEngine
from afre.probabilistic.artifacts import ProbabilisticForecast, ProbabilisticModelArtifact
from afre.probabilistic.definitions import ProbabilisticModelSpec, ThresholdDefinition
from afre.probabilistic.schema import DistributionFamily
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.service import ContextRequest, ServiceRepository
from afre.service import ServiceContextKind as K
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition
from afre.uncertainty.sources import source_for
from afre.universe.models import UniverseSnapshot
from examples.fusion_native import fuse_sources, horizon_fixture
from examples.health_native import native_monitor
from examples.orthogonalization_fixture import build_rows
from examples.uncertainty_fixture import UncertaintyFixture
from examples.uncertainty_fixture import build_fixture as native_fixture


@dataclass(frozen=True)
class ServiceFixture:
    native: UncertaintyFixture
    context_cases: tuple[tuple[str, tuple[ContextRequest, ...]], ...]
    horizons: tuple[tuple[int, str], ...]
    quantile_ids: tuple[str, ...] = ()

    def ids(self, name: str) -> tuple[str, ...]:
        return self.quantile_ids if name == "quantile" else self.native.ids(name)


def build_fixture(repo: ServiceRepository, reverse: bool = False) -> ServiceFixture:
    native = native_fixture(repo, reverse)
    empirical = repo.get(ProbabilisticForecast, native.ids("empirical")[0])
    quantile_spec = replace(
        repo.get(
            ProbabilisticModelSpec,
            repo.get(ProbabilisticModelArtifact, empirical.model_artifact_id).spec_id,
        ),
        family=DistributionFamily.QUANTILE_SET,
        thresholds=ThresholdDefinition(()),
    )
    probability = ProbabilisticEngine(repo)
    quantile_model = probability.fit_model(quantile_spec, 40, 40, 40)
    quantile_forecasts = probability.predict_batch(
        quantile_model.artifact_id, (empirical.input,)
    )
    gaussian = native.ids("gaussian")[0]
    source = source_for(repo, gaussian)
    universe = repo.get(
        UniverseSnapshot, repo.get(ResearchSample, source.sample_id).snapshot_id
    )
    rank_spec = CrossSectionSpec(
        CrossSectionIdentity(
            source.origin,
            universe.fingerprint,
            source.target,
            universe.definition.eligibility.fingerprint,
        ),
        ScoreSpec(
            ScoreSource.POINT_EXPECTATION,
            model_id=repo.get(ProbabilisticForecast, gaussian).model_artifact_id,
        ),
    )
    rank_sources = tuple(
        (repo.get(ResearchSample, source_for(repo, i).sample_id).security.fingerprint, i)
        for i in native.ids("gaussian")
    )
    ranking = CrossSectionEngine(repo).build_ranking(rank_spec, rank_sources)
    uncertainty = next(
        i
        for i in native.results("gaussian")
        if repo.get(ForecastUncertaintyDecomposition, i).forecast_id == gaussian
    )
    health = native_monitor(repo, native.ids("gaussian"), (HealthDiagnostic.PREDICTION_MEAN,))
    orth_spec, rows = build_rows(repo, source.fold_id, source.target, 40, tag="service")
    orth = OrthogonalizationEngine(repo)
    projection = orth.fit(
        orth_spec, tuple(r.fingerprint for r in rows if r.partition is Partition.TRAIN), 40
    )
    row = next(r for r in rows if r.sample_id == source.sample_id)
    residual = orth.residual(projection.fingerprint, row.fingerprint, row.origin.timestamp_ns)
    cases: list[tuple[str, tuple[ContextRequest, ...]]] = [
        (
            gaussian,
            (
                ContextRequest(K.RANKING, ranking.fingerprint),
                ContextRequest(K.UNCERTAINTY, uncertainty),
                ContextRequest(K.ORTHOGONAL, residual.fingerprint),
                ContextRequest(K.HEALTH, health.fingerprint, True),
            ),
        )
    ]
    event = next(i for i in native.ids("event") if getattr(repo.raw(i), "event_ids", ()))
    cases.append((event, (ContextRequest(K.EVENT, event),)))
    regime = next(
        i for i in native.ids("hard-regime") if getattr(repo.raw(i), "regime_snapshot_id", None)
    )
    cases.append((regime, (ContextRequest(K.REGIME, regime),)))
    mixture = native.ids("mixture")[0]
    sample = source_for(repo, mixture).sample_id
    matching = next(
        i for i in native.ids("gaussian") if source_for(repo, i).sample_id == sample
    )
    fused = fuse_sources(
        repo, "service-exact-mixture", (mixture, matching), FusionKind.PROBABILISTIC
    )
    cases.append((fused, (ContextRequest(K.FUSION, fused),)))
    engine = ChallengeEngine(repo)
    alternative = fuse_sources(
        repo, "service-challenger", (matching,), FusionKind.PROBABILISTIC
    )
    champion = engine.participant("service-champion", ParticipantRole.CHAMPION, fused)
    challenger = engine.participant(
        "service-challenger", ParticipantRole.CHALLENGER, alternative
    )
    ref = champion.reference
    assert ref.dataset_id is not None and ref.fold_id is not None
    at = source_for(repo, matching).origin.timestamp_ns
    request = ChallengeMetricRequest(ChallengeMetric.MAE, 1)
    criterion = PromotionCriterion(
        "service-improvement",
        request.fingerprint,
        ChallengeDirection.LOWER,
        0.0,
        1,
        ref.available_ns,
    )
    program = ChallengeProgram(
        "service-program",
        champion.fingerprint,
        (challenger.fingerprint,),
        ref.target_id,
        ref.horizon_id,
        ref.unit,
        ref.dataset_id,
        ref.fold_id,
        ChallengeWindow(at, at + 1, 120),
        1,
        (request,),
        (criterion.fingerprint,),
        (),
        ChallengeTestPolicy.VALIDATION_ONLY,
        ref.available_ns,
    )
    engine.declare(program, (criterion,))
    shadows = tuple(
        engine.shadow(program.fingerprint, participant.fingerprint, identity, at).fingerprint
        for participant, identity in ((champion, fused), (challenger, alternative))
    )
    sample_record = repo.get(ResearchSample, source_for(repo, matching).sample_id)
    assert sample_record.target_id is not None
    evidence = engine.evidence(
        EvaluationEvidence(
            program.fingerprint,
            shadows,
            ((sample_record.fingerprint, sample_record.target_id),),
            120,
        )
    )
    run = engine.evaluate(evidence.fingerprint)
    cases.append((fused, (ContextRequest(K.CHALLENGE, run.fingerprint, True),)))
    return ServiceFixture(
        native,
        tuple(cases),
        horizon_fixture(repo),
        tuple(p.fingerprint for p in quantile_forecasts),
    )
