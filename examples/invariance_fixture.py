"""One offline native AFRE-16 graph and declared AFRE-17 analysis inputs."""

from dataclasses import dataclass

from afre.invariance import (
    EnvironmentDefinition,
    EnvironmentKind,
    EnvironmentRule,
    EnvironmentSet,
    InvarianceEngine,
    InvarianceRepository,
    StabilityAnalysisSpec,
    StabilityMetricName,
    StabilitySampleMode,
    StabilityTimeWindow,
)
from afre.invariance.forecasts import forecast_source
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.statistical_models.artifacts import PointForecast
from examples.orthogonalization_fixture import OrthogonalFixture
from examples.orthogonalization_fixture import build_fixture as orthogonal_fixture


@dataclass(frozen=True)
class InvarianceFixture:
    upstream: OrthogonalFixture
    environment_set: EnvironmentSet
    spec: StabilityAnalysisSpec
    membership_ids: tuple[str, ...]


def native_forecasts(
    repo: InvarianceRepository,
    fixture: OrthogonalFixture,
    probability: bool = True,
    partition: Partition = Partition.VALIDATION,
) -> tuple[str, ...]:
    first = repo.get(ProbabilisticForecast, fixture.upstream.ids("gaussian")[0])
    point = repo.get(PointForecast, first.point_forecast_id)
    cls, table = (
        (ProbabilisticForecast, "p_artifacts")
        if probability
        else (PointForecast, "m_artifacts")
    )
    values = tuple(
        repo.get(cls, row[0])
        for row in repo._connection.execute(
            f"SELECT fingerprint FROM {table} WHERE type_name=? ORDER BY fingerprint",
            (cls.__name__,),
        )
    )
    assert all(isinstance(v, (ProbabilisticForecast, PointForecast)) for v in values)
    return tuple(
        v.fingerprint
        for v in values
        if isinstance(v, (ProbabilisticForecast, PointForecast))
        and v.model_artifact_id
        == (first.model_artifact_id if probability else point.model_artifact_id)
        and forecast_source(repo, v.fingerprint).partition is partition
    )


def declared_fixture(
    repo: InvarianceRepository, upstream: OrthogonalFixture, reverse: bool = False
) -> InvarianceFixture:
    target, fold = upstream.spec.target, upstream.spec.fold_id
    definitions = tuple(
        EnvironmentDefinition(
            name,
            EnvironmentKind.TIME_WINDOW,
            name,
            "1",
            "AFRE-declared",
            EnvironmentRule.TIME,
            target,
            40,
            window=StabilityTimeWindow(a, b),
        )
        for name, a, b in (("early", 40, 51), ("late", 50, 61))
    )
    engine = InvarianceEngine(repo)
    envset = engine.declare(
        EnvironmentSet(tuple(reversed(definitions)) if reverse else definitions, 40)
    )
    forecasts = native_forecasts(repo, upstream)
    samples = tuple(s.fingerprint for s in repo.partition_samples(fold, Partition.VALIDATION))
    metrics = tuple(StabilityMetricName)
    spec = StabilityAnalysisSpec(
        target,
        fold,
        envset.fingerprint,
        samples,
        forecasts,
        metrics,
        40,
        baseline_environment_id=definitions[0].fingerprint,
        feature_reference_ids=(
            upstream.spec.candidate.fingerprint,
            *(r.fingerprint for r in upstream.spec.references),
        ),
        sample_mode=StabilitySampleMode.SAME_ORIGIN_CROSS_SECTION,
    )
    engine.register(spec)
    members = tuple(
        engine.bind(
            d.fingerprint, sample, constructed_ns=repo.get(ResearchSample, sample).timestamp_ns
        ).fingerprint
        for d in (reversed(envset.definitions) if reverse else envset.definitions)
        for sample in (reversed(spec.sample_ids) if reverse else spec.sample_ids)
    )
    return InvarianceFixture(upstream, envset, spec, tuple(sorted(members)))


def build_fixture(repo: InvarianceRepository, reverse: bool = False) -> InvarianceFixture:
    return declared_fixture(repo, orthogonal_fixture(repo, reverse), reverse)
