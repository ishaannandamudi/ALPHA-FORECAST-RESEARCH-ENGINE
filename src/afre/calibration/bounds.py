"""Bounds applied before fitting/work allocation and again at persistence/read."""

from afre.calibration.artifacts import (
    CalibratedForecast,
    CalibrationDriftDiagnostics,
    CalibrationEvaluation,
    CalibrationLineageAudit,
    CalibrationObservationSet,
    CalibrationState,
    ConformalScoreSet,
    ProbabilityMapping,
    QuantileOffset,
)
from afre.calibration.definitions import (
    CalibrationBinDefinition,
    CalibrationDriftSpec,
    CalibrationPartition,
    CalibrationSpec,
)
from afre.calibration.schema import CalibrationBounds
from afre.schema import Artifact, require
from afre.serialization import canonical_json


def check_bounds(value: Artifact, b: CalibrationBounds) -> None:
    if isinstance(value, CalibrationSpec):
        check_bounds(value.partition, b)
        check_bounds(value.bins, b)
        require(
            len(value.quantiles.levels) <= b.quantiles
            and len(value.events.requests) <= b.events,
            "calibration quantile/event bound",
        )
    elif isinstance(value, CalibrationPartition):
        require(
            len(value.reserved_sample_ids) <= b.observations
            and (value.rolling_count is None or value.rolling_count <= b.rolling_window),
            "calibration reservation/window bound",
        )
    elif isinstance(value, CalibrationBinDefinition):
        require(len(value.edges) - 1 <= b.bins, "calibration bin bound")
    elif isinstance(value, CalibrationObservationSet):
        require(
            max(len(value.requests), len(value.rows), len(value.exclusions)) <= b.observations,
            "calibration observation bound",
        )
        require(
            all(
                len(r.quantiles) <= b.quantiles and len(r.probabilities) <= b.events
                for r in value.rows
            ),
            "observation output bound",
        )
    elif isinstance(value, ProbabilityMapping):
        require(
            len(value.blocks) <= b.blocks
            and len(value.bins) <= b.bins
            and (
                sum(len(x.observation_ids) for x in value.blocks)
                + sum(len(x.observation_ids) for x in value.bins)
            )
            <= b.observations,
            "mapping block/bin/evidence bound",
        )
    elif isinstance(value, QuantileOffset):
        require(len(value.residuals) <= b.observations, "offset score bound")
    elif isinstance(value, ConformalScoreSet):
        require(len(value.scores) <= b.conformal_scores, "conformal score bound")
    elif isinstance(value, CalibrationState):
        require(
            len(value.inputs.sample_ids) <= b.observations
            and len(value.mapping_ids) <= b.events
            and len(value.offset_ids) <= b.quantiles,
            "state evidence bound",
        )
    elif isinstance(value, CalibratedForecast):
        require(
            len(value.quantiles) <= b.quantiles and len(value.probabilities) <= b.events,
            "calibrated output bound",
        )
    elif isinstance(value, CalibrationEvaluation):
        require(
            len(value.forecast_ids) <= b.forecasts and len(value.pairs) <= b.observations,
            "evaluation forecast/pair bound",
        )
    elif isinstance(value, CalibrationDriftSpec):
        require(value.window_evaluations <= b.rolling_window, "drift window bound")
    elif isinstance(value, CalibrationDriftDiagnostics):
        require(
            max(len(value.evaluation_ids), len(value.windows)) <= b.diagnostics,
            "drift diagnostic bound",
        )
        check_bounds(value.spec, b)
    elif isinstance(value, CalibrationLineageAudit):
        require(len(value.evidence_ids) <= b.audit_nodes, "calibration audit node bound")
    require(
        len(canonical_json(value).encode()) <= b.serialized_bytes,
        "calibration payload byte bound",
    )
