"""Target-free extraction of exactly declared comparable forecast statistics."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibratedForecast
from afre.cross_sectional.artifacts import CrossSectionObservation, RawScore
from afre.cross_sectional.definitions import CrossSectionSpec, origin_context
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.models import CrossSectionPrediction
from afre.cross_sectional.schema import CrossSectionScoreState, ScoreSource, SignalQuality
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.schema import require
from afre.statistical_models.artifacts import PointForecast
from afre.statistical_models.linear_algebra import finite

if TYPE_CHECKING:
    from afre.cross_sectional.repository import CrossSectionRepository


def point_scaffold(repo: "CrossSectionRepository", source_id: str) -> PointForecast | None:
    value = repo.get_any(source_id)
    if isinstance(value, PointForecast):
        return value
    if isinstance(value, CrossSectionPrediction):
        return repo.resolve(PointForecast, value.scaffold_id)
    if isinstance(value, CalibratedForecast):
        value = repo.resolve(ProbabilisticForecast, value.raw_forecast_id)
    if isinstance(value, ProbabilisticForecast):
        return repo.resolve(PointForecast, value.point_forecast_id)
    return None


def score_for(
    repo: "CrossSectionRepository", spec: CrossSectionSpec, observation: CrossSectionObservation
) -> RawScore:
    require(
        observation.spec_id == spec.fingerprint
        and origin_context(observation.origin) == origin_context(spec.identity.anchor_origin),
        "mixed cross-section origins",
    )
    cutoff = observation.origin.availability_cutoff_ns

    def result(
        value: float | None, state: CrossSectionScoreState, at: int | None, reason: str
    ) -> RawScore:
        return RawScore(observation.fingerprint, observation.security, value, state, at, reason)

    if observation.source_id is None:
        return result(None, CrossSectionScoreState.MISSING, None, "required-source-missing")
    source = repo.get_any(observation.source_id)
    score = spec.score
    value: float | None = None
    if score.source is ScoreSource.EXTERNAL_SIGNAL:
        require(isinstance(source, ExternalSignal), "external source contract required")
        assert isinstance(source, ExternalSignal)
        require(
            source.security == observation.security
            and source.semantic_key
            == (
                score.provider_name,
                score.provider_version,
                score.provider_schema,
                score.signal_name,
                score.signal_version,
                score.signal_semantics,
                score.unit,
            ),
            "external signal semantics",
        )
        at = source.clocks.final_available_ns
        repo.approved(source.clocks.historical_delivery, spec.approved_delivery_attestors)
        if at > cutoff or source.as_of_ns > observation.origin.timestamp_ns:
            return result(
                None, CrossSectionScoreState.FUTURE, at, "external-not-received-by-origin"
            )
        if source.quality is not SignalQuality.VALID or (
            score.maximum_age_ns is not None
            and observation.origin.timestamp_ns - source.as_of_ns > score.maximum_age_ns
        ):
            return result(None, CrossSectionScoreState.INVALID, at, "external-quality-or-stale")
        if type(source.value) not in (int, float):
            return result(
                None, CrossSectionScoreState.UNSUPPORTED, at, "nonnumeric-external-score"
            )
        assert isinstance(source.value, (int, float))
        value = float(source.value)
    else:
        require(
            isinstance(
                source,
                (
                    PointForecast,
                    ProbabilisticForecast,
                    CalibratedForecast,
                    CrossSectionPrediction,
                ),
            ),
            "forecast source required",
        )
        assert isinstance(
            source,
            (PointForecast, ProbabilisticForecast, CalibratedForecast, CrossSectionPrediction),
        )
        scaffold = point_scaffold(repo, source.fingerprint)
        assert scaffold is not None
        require(
            scaffold.input.origin == observation.origin
            and scaffold.target_definition_id == spec.identity.target.fingerprint
            and scaffold.historical_admissible,
            "forecast origin/target/horizon mismatch",
        )
        at = source.available_ns
        if isinstance(source, CrossSectionPrediction):
            require(
                score.source is ScoreSource.POINT_PREDICTION
                and source.model_id == score.model_id,
                "relative score model",
            )
            value = source.value
        elif isinstance(source, PointForecast):
            require(
                score.source is ScoreSource.POINT_PREDICTION
                and not score.calibrated
                and source.model_artifact_id == score.model_id,
                "point score semantics",
            )
            value = source.value
        else:
            require(
                score.source is not ScoreSource.POINT_PREDICTION
                and score.calibrated == isinstance(source, CalibratedForecast),
                "raw/calibrated score",
            )
            require(
                (
                    source.state_id
                    if isinstance(source, CalibratedForecast)
                    else source.model_artifact_id
                )
                == score.model_id,
                "probability score model",
            )
            raw = (
                repo.resolve(ProbabilisticForecast, source.raw_forecast_id)
                if isinstance(source, CalibratedForecast)
                else source
            )
            qs = source.quantiles
            ps = (
                source.probabilities
                if isinstance(source, CalibratedForecast)
                else source.threshold_probabilities
            )
            if score.source is ScoreSource.POINT_EXPECTATION:
                value = (
                    raw.expected_value
                    if not isinstance(source, CalibratedForecast)
                    or source.full_distribution_preserved
                    else None
                )
            elif score.source in (ScoreSource.MEDIAN, ScoreSource.QUANTILE):
                level = 0.5 if score.source is ScoreSource.MEDIAN else score.quantile
                value = next((q.value for q in qs if q.level == level), None)
            else:
                value = next((p.probability for p in ps if p.request == score.event), None)
        repo._validate_links(source)
        if at > cutoff:
            return result(
                None, CrossSectionScoreState.FUTURE, at, "forecast-unavailable-at-origin"
            )
    return result(
        finite(value) if value is not None else None,
        CrossSectionScoreState.AVAILABLE
        if value is not None
        else CrossSectionScoreState.UNSUPPORTED,
        at,
        "available" if value is not None else "statistic-unsupported",
    )
