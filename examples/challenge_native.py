"""Native family comparison helpers retaining original outputs and producer lineage."""

from afre.challenger import (
    ChallengeDirection,
    ChallengeEngine,
    ChallengeMetric,
    ChallengeMetricRequest,
    ChallengeProgram,
    ChallengeRepository,
    ChallengeTestPolicy,
    ChallengeWindow,
    EvaluationEvidence,
    ParticipantRole,
    PromotionCriterion,
    ShadowMode,
)
from afre.fusion.artifacts import FusedForecast
from afre.orthogonalization.artifacts import OrthogonalSignalValue
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.statistical_models.artifacts import PointForecast
from afre.statistical_models.schema import PredictionScope
from afre.uncertainty.sources import source_for


def sample_origin(repo: ChallengeRepository, identity: str) -> tuple[str, int]:
    value = repo.get_any(identity)
    if isinstance(value, (OrthogonalSignalValue, FusedForecast)):
        return value.sample_id, value.origin.timestamp_ns
    source = source_for(repo, identity)
    return source.sample_id, source.origin.timestamp_ns


def panel_family(repo: ChallengeRepository, anchor: str) -> tuple[str, ...]:
    """Exact frozen point/Gaussian producer across its existing validation panel."""
    first = repo.get_any(anchor)
    assert isinstance(first, (PointForecast, ProbabilisticForecast))
    cls, table = (
        (PointForecast, "m_artifacts")
        if anchor.startswith("afre." + PointForecast.domain + ":")
        else (ProbabilisticForecast, "p_artifacts")
    )
    result = []
    for (identity,) in repo._connection.execute(
        f"SELECT fingerprint FROM {table} WHERE type_name=? ORDER BY fingerprint",
        (cls.__name__,),
    ):
        raw = repo.get(cls, identity)
        assert isinstance(raw, (PointForecast, ProbabilisticForecast))
        if (
            raw.model_artifact_id == first.model_artifact_id
            and raw.input.scope is PredictionScope.VALIDATION
        ):
            source = source_for(repo, identity)
            if source.partition is Partition.VALIDATION:
                result.append(identity)
    return tuple(result)


def native_challenge(
    repo: ChallengeRepository,
    champion_sources: tuple[str, ...],
    challenger_sources: tuple[str, ...],
    *,
    name: str = "native-challenge",
    start_ns: int | None = None,
    end_ns: int | None = None,
    declared_ns: int = 40,
    cutoff_ns: int = 100,
    predeclared: bool = True,
    environment_id: str | None = None,
    membership_ids: tuple[str, ...] = (),
    uncertainty_ids: tuple[str, ...] = (),
    metric: ChallengeMetric = ChallengeMetric.MAE,
) -> tuple[ChallengeProgram, EvaluationEvidence]:
    engine = ChallengeEngine(repo)
    champion = engine.participant(
        name + "-champion", ParticipantRole.CHAMPION, champion_sources[0]
    )
    challenger = engine.participant(
        name + "-challenger", ParticipantRole.CHALLENGER, challenger_sources[0]
    )
    times = tuple(sample_origin(repo, i)[1] for i in (*champion_sources, *challenger_sources))
    start = min(times) if start_ns is None else start_ns
    end = max(times) + 1 if end_ns is None else end_ns
    request = ChallengeMetricRequest(metric, 1)
    rule = PromotionCriterion(
        name + "-metric",
        request.fingerprint,
        ChallengeDirection.HIGHER if metric is ChallengeMetric.IC else ChallengeDirection.LOWER,
        0.0,
        1,
        declared_ns,
    )
    ref = champion.reference
    program = ChallengeProgram(
        name,
        champion.fingerprint,
        (challenger.fingerprint,),
        ref.target_id,
        ref.horizon_id,
        ref.unit,
        champion.dataset_id,
        champion.fold_id,
        ChallengeWindow(start, end, cutoff_ns),
        1,
        (request,),
        (rule.fingerprint,),
        (),
        ChallengeTestPolicy.VALIDATION_ONLY,
        declared_ns,
        predeclared=predeclared
        and max(champion.reference.available_ns, challenger.reference.available_ns)
        <= declared_ns,
        shadow_mode=ShadowMode.RECONSTRUCTED_NATIVE,
        environment_id=environment_id,
        membership_ids=membership_ids,
        uncertainty_ids=uncertainty_ids,
    )
    engine.declare(program, (rule,))
    shadows = tuple(
        engine.shadow(program.fingerprint, p.fingerprint, i, max(120, cutoff_ns)).fingerprint
        for p, sources in ((champion, champion_sources), (challenger, challenger_sources))
        for i in sources
        if program.window.contains(sample_origin(repo, i)[1])
    )
    samples = {sample_origin(repo, i)[0] for i in (*champion_sources, *challenger_sources)}
    truths = tuple(
        (s.fingerprint, s.target_id)
        for s in (repo.get(ResearchSample, i) for i in sorted(samples))
        if s.target_id is not None and program.window.contains(s.timestamp_ns)
    )
    evidence = EvaluationEvidence(program.fingerprint, shadows, truths, max(120, cutoff_ns))
    return program, evidence
