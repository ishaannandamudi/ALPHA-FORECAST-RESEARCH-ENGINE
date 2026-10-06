"""Explicit count, dimension, work, payload and lineage bounds."""

from dataclasses import fields, replace

import pytest

from afre.schema import Artifact, ContractError
from afre.sequence import (
    SequenceBounds,
    SequenceSnapshot,
    SequenceWindowMode,
    SequenceWindowSpec,
)
from afre.sequence.lineage import lineage_for
from tests.sequence.conftest import Case


@pytest.mark.parametrize(
    "field", [f.name for f in fields(SequenceBounds) if not f.name.startswith("_")]
)
@pytest.mark.parametrize("value", [0, 1_000_000_000])
def test_hard_positive_bounds(field: str, value: int) -> None:
    with pytest.raises(ContractError):
        replace(SequenceBounds(), **{field: value})


@pytest.mark.parametrize(
    "kind", ["spec", "window", "model", "transform", "forecast", "dataset", "snapshot", "bytes"]
)
def test_lower_bounds(case: Case, kind: str) -> None:
    value: Artifact
    model = case.fixture.models[0]
    if kind == "spec":
        value = case.fixture.specs[0]
    elif kind == "window":
        value = case.fixture.specs[0].window
    elif kind == "model":
        value = model
    elif kind == "transform":
        value = case.repo.get_any(model.transform_id)
    elif kind == "dataset":
        value = case.repo.get_any(model.dataset_id)
    elif kind == "snapshot":
        value = case.repo.get(SequenceSnapshot, case.forecast.snapshot_id)
    else:
        value = case.forecast
    bound = {"window": "length", "dataset": "training_rows", "bytes": "serialized_bytes"}.get(
        kind, "features"
    )
    case.repo.sequence_bounds = replace(SequenceBounds(), **{bound: 1})
    with pytest.raises(ContractError, match="bound"):
        case.repo._bounds(value)


@pytest.mark.parametrize("field", ["audit_nodes", "audit_depth", "serialized_bytes"])
def test_lineage_bound(case: Case, field: str) -> None:
    case.repo.sequence_bounds = replace(SequenceBounds(), **{field: 1})
    with pytest.raises(ContractError, match="bound"):
        lineage_for(case.repo, case.forecast.fingerprint)


def test_query_and_work_overflow(case: Case) -> None:
    case.repo.sequence_bounds = replace(SequenceBounds(), observations=1)
    with pytest.raises(ContractError, match="overflow"):
        case.repo.observation_ids(case.fixture.features, case.forecast.origin)
    case.repo.sequence_bounds = replace(SequenceBounds(), work_cells=1)
    with pytest.raises(ContractError, match="bounds"):
        case.engine.fit_transform(case.fixture.specs[0], case.fixture.bindings, 40, 40, 40)
    with pytest.raises(ContractError):
        SequenceWindowSpec(SequenceWindowMode.FIXED_OBSERVATION_COUNT, 129)
