"""Closed serialization and fail-closed calibration assumptions."""

import json
from collections.abc import Callable
from dataclasses import replace

import pytest

from afre.calibration import (
    CalibrationBinDefinition,
    CalibrationBounds,
    CalibrationDriftSpec,
    CalibrationMethod,
    CalibrationPartitionPolicy,
    CalibrationState,
    DriftMetric,
)
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json, deserialize
from tests.calibration.conftest import CalibrationCase


@pytest.mark.parametrize(
    "invalid",
    [
        lambda c: replace(c.fixture.spec, minimum_samples=0),
        lambda c: replace(c.fixture.spec, random_seed=-1),
        lambda c: replace(c.fixture.spec, cutoff_ns=-1),
        lambda c: replace(c.fixture.spec, implementation_version="future"),
        lambda c: replace(c.fixture.spec, interpolation_version="sort-output"),
        lambda c: replace(c.fixture.spec, quantile_estimator="mean"),
        lambda c: replace(c.fixture.spec, conformal_estimator="ordinary-interpolation"),
        lambda c: replace(c.fixture.spec, miscoverage_alpha=0.2),
        lambda c: replace(c.fixture.spec, method=CalibrationMethod.CONFORMAL_ABSOLUTE_RESIDUAL),
        lambda c: replace(
            c.fixture.spec,
            method=CalibrationMethod.CONFORMAL_ABSOLUTE_RESIDUAL,
            miscoverage_alpha=0.0,
        ),
        lambda c: replace(
            c.fixture.spec,
            method=CalibrationMethod.CONFORMAL_ABSOLUTE_RESIDUAL,
            miscoverage_alpha=1.0,
        ),
        lambda c: replace(
            c.fixture.spec,
            method=CalibrationMethod.CONFORMAL_ABSOLUTE_RESIDUAL,
            miscoverage_alpha=0.1,
        ),
        lambda c: replace(
            c.fixture.spec, method=CalibrationMethod.ROLLING_CONFORMAL, miscoverage_alpha=0.2
        ),
        lambda c: replace(
            c.fixture.spec,
            method=CalibrationMethod.ISOTONIC_PROBABILITY,
            events=replace(c.fixture.spec.events, requests=()),
        ),
        lambda c: replace(c.fixture.spec.partition, reserved_sample_ids=()),
        lambda c: replace(
            c.fixture.spec.partition,
            reserved_sample_ids=c.fixture.spec.partition.reserved_sample_ids * 2,
        ),
        lambda c: replace(c.fixture.spec.partition, rolling_count=3),
        lambda c: replace(
            c.fixture.spec.partition, policy=CalibrationPartitionPolicy.ROLLING_PAST
        ),
        lambda c: replace(
            c.fixture.spec.partition,
            policy=CalibrationPartitionPolicy.ROLLING_PAST,
            rolling_count=0,
        ),
        lambda c: replace(c.fixture.spec.partition, strict_disjoint=False),
        lambda c: replace(c.fixture.spec.partition, window_basis="future-window"),
    ],
)
def test_invalid_fixed_contracts(
    calibration_case: CalibrationCase, invalid: Callable[[CalibrationCase], Artifact]
) -> None:
    with pytest.raises(ContractError):
        invalid(calibration_case)


@pytest.mark.parametrize(
    "edges", [(0.1, 1.0), (0.0, 0.5, 0.5, 1.0), (0.0, 1.1), (0.0,), (0.0, float("nan"), 1.0)]
)
def test_invalid_bins(edges: tuple[float, ...]) -> None:
    with pytest.raises(ContractError):
        CalibrationBinDefinition(edges)


@pytest.mark.parametrize(
    "field",
    [
        "observations",
        "bins",
        "blocks",
        "quantiles",
        "events",
        "conformal_scores",
        "rolling_window",
        "forecasts",
        "evaluations",
        "diagnostics",
        "audit_nodes",
        "work_cells",
    ],
)
def test_positive_bounds(field: str) -> None:
    with pytest.raises(ContractError):
        replace(CalibrationBounds(), **{field: 0})


@pytest.mark.parametrize(
    "field", ["bins", "quantiles", "events", "audit_depth", "serialized_bytes"]
)
def test_hard_bound_ceilings(field: str) -> None:
    with pytest.raises(ContractError):
        replace(CalibrationBounds(), **{field: 2**25})


def test_closed_roundtrip_unknown_payload_and_read(calibration_case: CalibrationCase) -> None:
    c = calibration_case
    for method in CalibrationMethod:
        run = c.fit(method)
        state = c.repo.get(CalibrationState, run.state_id)
        for identity in (
            run.fingerprint,
            state.fingerprint,
            state.inputs.fingerprint,
            state.inputs.observations_id,
            *state.mapping_ids,
            *state.offset_ids,
            *((state.conformal_id,) if state.conformal_id else ()),
            state.diagnostics_id,
        ):
            artifact = c.repo.get_any(identity)
            assert deserialize(canonical_json(artifact)) == artifact
    spec_payload = json.loads(canonical_json(c.fixture.spec))
    spec_payload["artifact"]["fields"]["method"] = {
        "$enum": "CalibrationMethod",
        "value": "external_executable",
    }
    with pytest.raises(ContractError):
        deserialize(json.dumps(spec_payload, sort_keys=True, separators=(",", ":")))
    with pytest.raises(KeyError):
        c.repo.get(CalibrationState, "afre.c_state:1.0:" + "0" * 64)
    with pytest.raises(ContractError, match="unresolved"):
        c.repo.get_any("afre.c_executable:1.0:" + "0" * 64)
    with pytest.raises(ContractError):
        CalibrationDriftSpec(0, 1, DriftMetric.ECE, 0.1)
    with pytest.raises(ContractError):
        CalibrationBinDefinition(minimum_count=0)
