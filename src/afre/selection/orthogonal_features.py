"""Explicit causal AFRE16 residual projection into native AFRE13 scalar features."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.cross_sectional.engine import CrossSectionEngine
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.schema import SignalQuality
from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.hashing import bytes_digest
from afre.lineage import ProvenanceRef
from afre.nonlinear.artifacts import NonlinearInput, ScalarInput
from afre.nonlinear.definitions import NonlinearModelSpec
from afre.nonlinear.engine import NonlinearEngine
from afre.orthogonalization.artifacts import OrthogonalSignalValue
from afre.research_datasets.samples import ResearchSample
from afre.schema import Artifact, contract, require
from afre.selection.definitions import NativeCandidateRecipe
from afre.serialization import canonical_json

if TYPE_CHECKING:
    from afre.selection.repository import SelectionRepository


@contract("sel_orthogonal_feature")
@dataclass(frozen=True, slots=True)
class OrthogonalFeatureBinding(Artifact):
    residual_id: str
    scalar_id: str


def publish_orthogonal_feature(
    repo: "SelectionRepository", residual_id: str
) -> OrthogonalFeatureBinding:
    residual = repo.resolve(OrthogonalSignalValue, residual_id)
    sample = repo.get(ResearchSample, residual.sample_id)
    require(
        residual.residual is not None and sample.origin == residual.origin,
        "exact available causal residual feature",
    )
    source = SourceReference(
        ProvenanceRef(
            "AFRE16-residual",
            "residual-feature-v1",
            "1",
            bytes_digest(canonical_json(residual).encode()),
        ),
        residual.projection_id,
    )
    at = residual.available_ns
    signal = ExternalSignal(
        "AFRE16-residual",
        "1",
        "1.0",
        sample.security,
        "declared.orthogonal.residual",
        "1",
        "causal-native-residual-projection-v1",
        residual.origin.timestamp_ns,
        AvailabilityEvidence(at, at, at, at),
        residual.residual,
        residual.unit,
        SignalQuality.VALID,
        source,
    )
    CrossSectionEngine(repo).publish_external(signal)
    scalar = NonlinearEngine(repo).scalar(signal.fingerprint, residual.origin)
    binding = OrthogonalFeatureBinding(residual_id, scalar.fingerprint)
    with repo.transaction():
        repo.put(binding)
    return binding


def validate_binding(repo: "SelectionRepository", value: OrthogonalFeatureBinding) -> None:
    residual = repo.resolve(OrthogonalSignalValue, value.residual_id)
    scalar = repo.resolve(ScalarInput, value.scalar_id)
    signal = repo.resolve(ExternalSignal, scalar.source_id)
    require(
        residual.residual is not None
        and scalar.value == residual.residual
        and scalar.origin == residual.origin
        and scalar.available_ns >= residual.available_ns
        and signal.source.dataset_id == residual.projection_id
        and signal.source.provenance.payload_sha256
        == bytes_digest(canonical_json(residual).encode())
        and signal.signal_semantics == "causal-native-residual-projection-v1",
        "orthogonal feature exact residual/value/origin/availability/lineage",
    )


def validate_orthogonal_features(
    repo: "SelectionRepository", recipe: NativeCandidateRecipe
) -> None:
    require(
        isinstance(recipe.native_spec, NonlinearModelSpec),
        "residual feature adapter supports native nonlinear scalar inputs",
    )
    spec = recipe.native_spec
    assert isinstance(spec, NonlinearModelSpec)
    packets = tuple(
        repo.resolve(NonlinearInput, i)
        for i in (*recipe.train_input_ids, *(i for _, i in recipe.validation_bindings))
    )
    for identity in recipe.orthogonal_feature_ids:
        binding = repo.resolve(OrthogonalFeatureBinding, identity)
        scalar = repo.resolve(ScalarInput, binding.scalar_id)
        require(
            scalar.definition in spec.features and any(scalar in p.scalars for p in packets),
            "declared residual must actually be consumed as a candidate feature",
        )
