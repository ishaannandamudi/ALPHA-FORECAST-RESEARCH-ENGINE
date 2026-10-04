"""Explicit reservations on unchanged AFRE-4 memberships, strict model holdout."""

from typing import TYPE_CHECKING

from afre.calibration.definitions import CalibrationSpec
from afre.calibration.schema import CalibrationOverlapStatus, CalibrationPartitionPolicy
from afre.probabilistic.artifacts import (
    ProbabilisticFitInputs,
    ProbabilisticForecast,
    ProbabilisticModelArtifact,
)
from afre.probabilistic.definitions import ProbabilisticModelSpec
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import FoldDefinition
from afre.schema import require
from afre.statistical_models.schema import PredictionScope

if TYPE_CHECKING:
    from afre.calibration.repository import CalibrationRepository


def overlap_status(
    sample_ids: tuple[str, ...], train_ids: tuple[str, ...] | None
) -> CalibrationOverlapStatus:
    if train_ids is None:
        return CalibrationOverlapStatus.UNKNOWN
    return (
        CalibrationOverlapStatus.OVERLAPS_MODEL_TRAIN
        if set(sample_ids) & set(train_ids)
        else CalibrationOverlapStatus.DISJOINT_FROM_MODEL_TRAIN
    )


def spec_context(
    repo: "CalibrationRepository", spec: CalibrationSpec
) -> ProbabilisticFitInputs:
    repo.check_calibration_bounds(spec)
    model = repo.resolve(ProbabilisticModelArtifact, spec.raw_model_id)
    raw = repo.resolve(ProbabilisticModelSpec, model.spec_id)
    inputs = repo.resolve(ProbabilisticFitInputs, model.fit_inputs_id)
    require(
        model.spec_id == spec.raw_spec_id and raw.target == spec.target,
        "raw model/spec/target horizon mismatch",
    )
    require(
        spec.cutoff_ns >= model.available_ns, "calibration cutoff before raw model availability"
    )
    require(
        set(spec.events.requests) <= set(raw.thresholds.requests)
        and set(spec.quantiles.levels) <= set(raw.quantiles.levels),
        "raw event/quantile identity mismatch",
    )
    fold = repo.resolve(FoldDefinition, spec.partition.fold_id)
    require(fold.dataset_id == inputs.dataset_id, "calibration partition dataset mismatch")
    rows = repo._connection.execute(
        "SELECT fingerprint FROM p_fits WHERE artifact_id=?", (spec.raw_model_id,)
    ).fetchall()
    require(len(rows) == 1, "calibration requires completed raw probabilistic fit")
    return inputs


def eligible_forecasts(
    repo: "CalibrationRepository",
    spec: CalibrationSpec,
    forecasts: tuple[ProbabilisticForecast, ...],
) -> CalibrationOverlapStatus:
    inputs = spec_context(repo, spec)
    partition = spec.partition
    # Validate the whole reservation before reading any calibration truth, including TEST.
    allowed = (
        (Partition.TRAIN,)
        if partition.policy is CalibrationPartitionPolicy.TRAIN_TAIL
        else (Partition.TRAIN, Partition.VALIDATION)
    )
    reserved = set(partition.reserved_sample_ids)
    admitted = {
        s.fingerprint: s
        for group in allowed
        for s in repo.partition_samples(partition.fold_id, group)
    }
    require(
        reserved <= admitted.keys(),
        "calibration reservation includes TEST or inadmissible partition",
    )
    for identity in reserved:
        sample = admitted[identity]
        require(
            partition.origin_range.contains(sample.timestamp_ns)
            and sample.target_definition_id == spec.target.fingerprint,
            "calibration reservation origin/target mismatch",
        )
    status = overlap_status(partition.reserved_sample_ids, inputs.train_sample_ids)
    require(
        status is CalibrationOverlapStatus.DISJOINT_FROM_MODEL_TRAIN,
        "strict-disjoint calibration overlaps model TRAIN",
    )
    raw_fold_memberships = {
        m.sample_id: m.partition for m in repo.fold_memberships(inputs.fold_id)
    }
    for raw in forecasts:
        sample_id = raw.input.sample_id
        require(sample_id is not None, "calibration needs pinned sample")
        assert sample_id is not None
        require(
            raw.input.scope not in (PredictionScope.TEST, PredictionScope.IN_SAMPLE),
            "TEST/in-sample cannot fit calibration",
        )
        require(
            raw.input.sample_id in reserved and raw.input.sample_id not in (None,),
            "unreserved calibration forecast",
        )
        require(
            raw_fold_memberships.get(sample_id) not in (Partition.TEST, Partition.TRAIN),
            "underlying raw fold forbids TEST/TRAIN calibration",
        )
        require(
            raw.model_artifact_id == spec.raw_model_id
            and raw.target_definition_id == spec.target.fingerprint,
            "calibration raw forecast model/target mismatch",
        )
        sample = repo.resolve(ResearchSample, sample_id)
        require(sample.origin == raw.input.origin, "raw calibration origin mismatch")
        require(
            raw.historical_admissible
            and raw.available_ns <= raw.input.origin.availability_cutoff_ns
            and raw.input.origin.timestamp_ns < spec.cutoff_ns,
            "raw forecast did not exist historically before calibration cutoff",
        )
    return status
