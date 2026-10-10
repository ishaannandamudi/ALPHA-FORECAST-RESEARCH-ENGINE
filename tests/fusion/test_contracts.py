"""Closed compatibility contracts, duplicates and safe canonical data."""

import json
from dataclasses import FrozenInstanceError, replace
from enum import Enum

import pytest

from afre.fusion import (
    ExternalFusionOutput,
    FusionEngine,
    FusionFamily,
    FusionKind,
    FusionNormalization,
    FusionObservation,
    FusionRepository,
    FusionWeights,
)
from afre.fusion.external import ExternalFusionDefinition
from afre.schema import ContractError
from afre.serialization import canonical_json, deserialize
from examples.fusion_fixture import FusionFixture

Case = tuple[FusionRepository, FusionFixture]


@pytest.mark.parametrize(
    "field,value",
    (
        ("seed", -1),
        ("seed", 2**32),
        ("tolerance", 0.0),
        ("rank_tolerance", 1.0),
        ("condition_limit", 0.9),
        ("implementation", "unknown"),
        ("family", FusionFamily.FIXED_PROBABILITY_MIXTURE),
        ("kind", FusionKind.SCALAR_SIGNAL),
        ("normalization", FusionNormalization.TRAIN_STANDARDIZE),
        ("weight_policy", FusionWeights.UNCONSTRAINED_QR),
    ),
)
def test_closed_spec_policies(fusion_case: Case, field: str, value: object) -> None:
    _, f = fusion_case
    with pytest.raises(ContractError):
        wire = json.loads(canonical_json(f.spec))
        wire["artifact"]["fields"][field] = (
            {"$enum": type(value).__name__, "value": value.value}
            if isinstance(value, Enum)
            else value
        )
        deserialize(json.dumps(wire))


def test_duplicate_versions_and_incompatible_units(fusion_case: Case) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    first = f.references[0]
    raw = repo.get(
        ExternalFusionOutput,
        repo.get(FusionObservation, f.observations(f.validation[0])[0]).output_id,
    )
    definition = repo.get(ExternalFusionDefinition, raw.definition_id)
    new_definition = replace(definition, version="2")
    output = replace(raw, definition_id=new_definition.fingerprint, revision="2")
    e.external(new_definition, (output,))
    second = e.source(output.fingerprint)
    original_ref = next(r for r in f.references if r.source_id == second.source_id)
    spec = replace(
        f.spec,
        source_ids=(original_ref.fingerprint, second.fingerprint),
        weights=((original_ref.fingerprint, 0.5), (second.fingerprint, 0.5)),
    )
    with pytest.raises(ContractError, match="duplicate logical"):
        e.declare(spec)
    e.declare(replace(spec, allow_distinct_versions=True))
    with pytest.raises(ContractError, match="INCOMPATIBLE"):
        e.declare(replace(f.spec, unit="ordinal-rank"))
    with pytest.raises(ContractError, match="source grid"):
        replace(f.spec, source_ids=(first.fingerprint, first.fingerprint))
    assert second.version == "2"


def test_immutable_safe_canonical_artifacts(fusion_case: Case) -> None:
    repo, f = fusion_case
    assert deserialize(canonical_json(f.spec)) == f.spec
    with pytest.raises(FrozenInstanceError):
        f.spec.__setattr__("name", "mutated")
    with pytest.raises(ContractError, match="unsupported"):
        FusionEngine(repo).source(f.spec.target_id)
    with pytest.raises(ContractError, match="typed explicit"):
        FusionEngine(repo).source(f.references[0].anchor_output_id, "POINT")
