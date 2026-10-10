"""Neutral external forecast contracts with separate publication and receipt clocks."""

from dataclasses import dataclass

from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.forecast import ForecastOrigin
from afre.fusion.probabilistic import Law
from afre.fusion.schema import FusionKind
from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require
from afre.target_engine.definitions import TargetDefinition


@contract("fus_external_definition")
@dataclass(frozen=True, slots=True)
class ExternalFusionDefinition(Artifact):
    logical_id: str
    provider: str
    version: str
    target: TargetDefinition
    kind: FusionKind
    unit: str
    source: SourceReference
    declared_ns: int
    base_fit_cutoff_ns: int = 0
    base_train_sample_ids: tuple[str, ...] = ()
    protocol: str = "external-fixed-historical-v1"

    def _normalize(self) -> None:
        object.__setattr__(
            self, "base_train_sample_ids", tuple(sorted(self.base_train_sample_ids))
        )

    def _validate(self) -> None:
        require(self.source.provenance.system == self.provider, "external provider/source")
        require(
            self.protocol in ("external-fixed-historical-v1", "external-out-of-sample-v1")
            and len(set(self.base_train_sample_ids)) == len(self.base_train_sample_ids) <= 2000,
            "external declared historical prediction evidence",
        )
        require(
            self.protocol != "external-fixed-historical-v1"
            or not self.base_train_sample_ids
            and self.base_fit_cutoff_ns == 0,
            "fixed external producer cannot hide fitted evidence",
        )
        for i in self.base_train_sample_ids:
            validate_fingerprint(i, "r_sample")


@contract("fus_external_output")
@dataclass(frozen=True, slots=True)
class ExternalFusionOutput(Artifact):
    definition_id: str
    sample_id: str
    origin: ForecastOrigin
    value: float | None
    law: Law | None
    clocks: AvailabilityEvidence
    revision: str

    def _validate(self) -> None:
        validate_fingerprint(self.definition_id, "fus_external_definition")
        validate_fingerprint(self.sample_id, "r_sample")
        require(
            self.law is None or self.value is not None, "external law requires point witness"
        )
