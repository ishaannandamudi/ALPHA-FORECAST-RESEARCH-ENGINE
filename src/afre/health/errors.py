"""Later-cutoff exact native truth joins, with TEST seals checked before target reads."""

from math import fsum, sqrt
from statistics import fmean, pvariance
from typing import TYPE_CHECKING

from afre.health.artifacts import HealthObservation
from afre.health.definitions import (
    HealthDiagnosticRequest,
    HealthSpec,
    MonitoredArtifactReference,
)
from afre.health.schema import HealthDiagnostic as D
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import require
from afre.statistical_models.metrics import correlation, point_metrics
from afre.statistical_models.schema import MetricName
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository


def truth_for(
    repo: "HealthRepository", spec: HealthSpec, observation: HealthObservation, cutoff_ns: int
) -> TargetVintage | None:
    require(
        "input-grid" not in observation.quality, "input grids are not target-unit forecasts"
    )
    if observation.sample_id is None:
        return None
    ref = repo.get(MonitoredArtifactReference, observation.reference_id)
    require(
        ref.unit == "target-value:" + spec.target_id, "health errors require exact target units"
    )
    sample = repo.resolve(ResearchSample, observation.sample_id)
    require(
        sample.origin is not None and sample.target_definition_id == spec.target_id,
        "health exact truth sample/target",
    )
    if observation.partition is Partition.TEST:
        from afre.fusion.artifacts import FrozenFusionTestChoice, FusedForecast
        from afre.fusion.sources import FAMILIES

        source = repo.get_any(observation.source_id)
        if isinstance(source, FusedForecast):
            choices = tuple(
                repo.resolve(FrozenFusionTestChoice, row[0])
                for row in repo._connection.execute(
                    "SELECT fingerprint FROM fus_artifacts WHERE "
                    "type_name='FrozenFusionTestChoice'"
                )
            )
            require(
                any(c.artifact_id == source.artifact_id for c in choices),
                "health retains native frozen fusion TEST choice",
            )
        else:
            require(type(source).__name__ in FAMILIES, "unsupported TEST scalar truth bridge")
        require(
            spec.predeclared and spec.test_evaluation_id is not None,
            "health TEST truth requires predeclared sealed protocol",
        )
        assert spec.test_evaluation_id is not None
        seal = repo.resolve(TestEvaluation, spec.test_evaluation_id)
        require(
            seal.fold_id == ref.fold_id
            and observation.sample_id in seal.sample_ids
            and seal.evaluated_ns
            == max(
                spec.reference_window.evaluation_cutoff_ns,
                spec.current_window.evaluation_cutoff_ns,
            ),
            "health exact native TEST seal/fold/sample/cutoff",
        )
    if sample.target_id is None:
        return None
    target = repo.resolve(TargetVintage, sample.target_id)
    require(
        target.origin == sample.origin and target.definition.fingerprint == spec.target_id,
        "health exact target vintage/origin",
    )
    return target if target_known_by_cutoff(target, cutoff_ns) else None


def error_score(
    request: HealthDiagnosticRequest, rows: tuple[tuple[HealthObservation, float, float], ...]
) -> float | None:
    p, y = tuple(r[1] for r in rows), tuple(r[2] for r in rows)
    errors = tuple(a - b for a, b in zip(p, y, strict=True))
    k = request.kind
    if k is D.BIAS:
        return fmean(errors)
    if k is D.MAE:
        return fmean(abs(e) for e in errors)
    if k is D.MSE:
        return fmean(e * e for e in errors)
    if k is D.RMSE:
        return sqrt(fmean(e * e for e in errors))
    if k is D.ERROR_VARIANCE:
        return pvariance(errors)
    if k is D.ERROR_QUANTILE:
        from afre.research_datasets.preprocessing import quantile

        return quantile(errors, request.quantile_level)
    if k is D.R_SQUARED:
        return next(m.value for m in point_metrics(p, y) if m.name is MetricName.R_SQUARED)
    if k in (D.IC, D.RANK_IC):
        correlations = []
        for at in sorted({r[0].valid_ns for r in rows}):
            group = tuple(r for r in rows if r[0].valid_ns == at)
            if len(group) < request.minimum_count:
                continue
            result = correlation(
                tuple(r[1] for r in group),
                tuple(r[2] for r in group),
                MetricName.SPEARMAN_CORRELATION
                if k is D.RANK_IC
                else MetricName.PEARSON_CORRELATION,
            )
            if result.value is not None:
                correlations.append(result.value)
        return fsum(correlations) / len(correlations) if correlations else None
    return None
