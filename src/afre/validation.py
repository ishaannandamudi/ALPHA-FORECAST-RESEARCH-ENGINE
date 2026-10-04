"""Pure boundary validation; eligibility is not a dataset-building pipeline."""

from afre.datasets import ForecastFeatureRow
from afre.experiments import ExperimentResult
from afre.models import ModelArtifact
from afre.providers import EventSnapshotRef
from afre.schema import require
from afre.targets import ForecastTargetRow
from afre.time import validate_timestamp


def validate_training_pair(
    features: ForecastFeatureRow, target: ForecastTargetRow, training_cutoff_ns: int
) -> None:
    validate_timestamp(training_cutoff_ns)
    require(features.origin == target.origin, "feature/target origins differ")
    require(target.target in features.dataset.targets, "target not declared by dataset")
    require(
        target.market_dataset_id in features.dataset.source_dataset_ids,
        "target market source not declared by dataset",
    )
    require(
        target.eligible_at(training_cutoff_ns), "future or invalid label excluded from training"
    )


def validate_snapshot_as_of(snapshot: EventSnapshotRef, requested_ns: int) -> None:
    validate_timestamp(requested_ns)
    require(
        snapshot.known_as_of_ns <= requested_ns and snapshot.available_ns <= requested_ns,
        "provider returned a future snapshot",
    )


def validate_result_model(result: ExperimentResult, model: ModelArtifact) -> None:
    require(result.model_artifact_id == model.fingerprint, "result/model reference mismatch")
    require(result.spec.model == model.spec, "result/model specification mismatch")
    require(
        result.spec.dataset.fingerprint == model.training_dataset_id,
        "result/model dataset mismatch",
    )
    require(
        result.spec.split.training_cutoff_ns == model.fit_cutoff_ns,
        "result/model training cutoff mismatch",
    )
    require(model.created_available_ns <= result.created_available_ns, "future model artifact")
