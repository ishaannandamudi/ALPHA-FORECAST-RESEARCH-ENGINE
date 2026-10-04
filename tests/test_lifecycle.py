from dataclasses import replace
from typing import Any

import pytest

from afre.evaluation import MetricRecord
from afre.experiments import ExperimentResult, ExperimentStatus
from afre.hashing import bytes_digest
from afre.models import ModelArtifact, ModelArtifactFormat
from afre.providers import EventSnapshotRef
from afre.schema import ContractError
from afre.time import DAY_NS, TimeRange
from afre.validation import validate_snapshot_as_of
from examples.foundation_demo import Demo


@pytest.mark.parametrize(
    "changes",
    [
        {"random_seed": 43},
        {"model": "not_a_model"},
    ],
)
def test_invalid_experiment(demo: Demo, changes: dict[str, Any]) -> None:
    with pytest.raises(ContractError):
        replace(demo.experiment, **changes)


def test_model_experiment_agreement(demo: Demo) -> None:
    with pytest.raises(ContractError):
        replace(
            demo.experiment,
            model=replace(
                demo.experiment.model,
                feature_set=replace(
                    demo.experiment.model.feature_set,
                    definitions=(demo.features[0].definition,),
                ),
            ),
        )
    with pytest.raises(ContractError):
        replace(
            demo.experiment,
            model=replace(
                demo.experiment.model,
                target=replace(demo.target.target, implementation_version="other"),
            ),
        )
    with pytest.raises(ContractError):
        replace(
            demo.experiment,
            dataset=replace(demo.row.dataset, origins=TimeRange(2 * DAY_NS, 24 * DAY_NS)),
        )
    for seed in (-1, 2**64, True):
        with pytest.raises(ContractError):
            replace(demo.experiment.model, random_seed=seed)


@pytest.mark.parametrize(
    "changes",
    [
        {"training_cutoff_ns": 16 * DAY_NS},
        {"training_cutoff_ns": 14 * DAY_NS},
        {"test": TimeRange(19 * DAY_NS, 25 * DAY_NS)},
        {"embargo_ns": 3 * DAY_NS},
        {"evaluation_cutoff_ns": 24 * DAY_NS},
        {"purge_overlapping_labels": False},
    ],
)
def test_split_invariants(demo: Demo, changes: dict[str, Any]) -> None:
    with pytest.raises(ContractError):
        replace(demo.experiment.split, **changes)


def artifact(demo: Demo) -> ModelArtifact:
    return ModelArtifact(
        demo.experiment.model,
        demo.row.dataset.fingerprint,
        demo.experiment.split.training_cutoff_ns,
        bytes_digest(b"synthetic-metadata"),
        ModelArtifactFormat.CANONICAL_JSON,
        (),
        15 * DAY_NS,
    )


def result(demo: Demo) -> ExperimentResult:
    metric = MetricRecord("crps", "metadata-test-v1", 0.02, 10, demo.experiment.split.test)
    return ExperimentResult(
        demo.experiment,
        ExperimentStatus.COMPLETED,
        (demo.row.dataset.fingerprint,),
        (metric,),
        artifact(demo).fingerprint,
        27 * DAY_NS,
    )


def test_artifact_metadata(demo: Demo) -> None:
    model = artifact(demo)
    for changes in (
        {"created_available_ns": model.fit_cutoff_ns - 1},
        {"training_dataset_id": demo.target.fingerprint},
        {"artifact_sha256": "bad"},
        {"metric_ids": (demo.target.fingerprint,)},
        {"format": "pickle"},
    ):
        with pytest.raises(ContractError):
            replace(model, **changes)
    metric = result(demo).metrics[0]
    assert replace(model, metric_ids=(metric.fingerprint,)).metric_ids == (metric.fingerprint,)
    with pytest.raises(ContractError):
        replace(model, metric_ids=(metric.fingerprint, metric.fingerprint))


@pytest.mark.parametrize(
    "changes",
    [
        {"model_artifact_id": None},
        {"created_available_ns": 26 * DAY_NS},
        {"input_ids": ()},
        {"input_ids": ("bad",)},
        {"model_artifact_id": "bad"},
        {"failure_reason": "unexpected"},
    ],
)
def test_invalid_completed_result(demo: Demo, changes: dict[str, Any]) -> None:
    with pytest.raises(ContractError):
        replace(result(demo), **changes)


def test_result_lifecycle_and_metrics(demo: Demo) -> None:
    completed = result(demo)
    planned = replace(
        completed,
        status=ExperimentStatus.PLANNED,
        metrics=(),
        model_artifact_id=None,
        created_available_ns=0,
    )
    failed = replace(
        planned, status=ExperimentStatus.FAILED, failure_reason="synthetic failure"
    )
    assert len({planned.fingerprint, failed.fingerprint, completed.fingerprint}) == 3
    with pytest.raises(ContractError):
        replace(planned, status=ExperimentStatus.FAILED)
    for inputs in ((demo.instrument.fingerprint,), (demo.row.dataset.fingerprint,) * 2):
        with pytest.raises(ContractError):
            replace(completed, input_ids=inputs)
    metric = completed.metrics[0]
    with pytest.raises(ContractError):
        replace(metric, sample_count=0)
    for changed in (
        replace(metric, name="undeclared"),
        replace(metric, origins=TimeRange(0, 25 * DAY_NS)),
    ):
        with pytest.raises(ContractError):
            replace(completed, metrics=(changed,))
    with pytest.raises(ContractError):
        replace(planned, metrics=(metric,))
    for metrics in ((), ("crps", "crps")):
        with pytest.raises(ContractError):
            replace(demo.experiment.evaluation, metrics=metrics)


def test_eie_snapshot_boundary(demo: Demo) -> None:
    snapshot = EventSnapshotRef(
        demo.instrument,
        "neutral-eie-snapshot",
        demo.origin.timestamp_ns,
        demo.origin.timestamp_ns,
        "eie-external-v1",
        ("snapshot-1.0", "event-1.0"),
        demo.features[0].lineage.upstream,
    )
    validate_snapshot_as_of(snapshot, demo.origin.timestamp_ns)
    assert (
        replace(snapshot, schema_versions=tuple(reversed(snapshot.schema_versions))) == snapshot
    )
    with pytest.raises(ContractError):
        validate_snapshot_as_of(snapshot, demo.origin.timestamp_ns - 1)
    for changes in (
        {"available_ns": snapshot.known_as_of_ns + 1},
        {"schema_versions": ()},
        {"components": ()},
        {"schema_versions": ("1.0", "1.0")},
    ):
        with pytest.raises(ContractError):
            replace(snapshot, **changes)


def test_result_model_lineage(demo: Demo) -> None:
    from afre.validation import validate_result_model

    completed, model = result(demo), artifact(demo)
    validate_result_model(completed, model)
    with pytest.raises(ContractError, match="reference"):
        validate_result_model(
            replace(completed, model_artifact_id="afre.model_artifact:1.0:" + "0" * 64), model
        )
    different_dataset = replace(demo.row.dataset, name="other-dataset")
    for changed in (
        replace(model, spec=replace(model.spec, family="other")),
        replace(model, training_dataset_id=different_dataset.fingerprint),
        replace(model, fit_cutoff_ns=model.fit_cutoff_ns - 1),
        replace(model, created_available_ns=completed.created_available_ns + 1),
    ):
        paired = replace(completed, model_artifact_id=changed.fingerprint)
        with pytest.raises(ContractError):
            validate_result_model(paired, changed)
