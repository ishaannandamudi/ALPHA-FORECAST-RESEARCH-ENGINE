"""Typed feature definitions and values, separate from target contracts."""

from dataclasses import dataclass
from enum import Enum

from afre.forecast import ForecastOrigin
from afre.ids import InstrumentId, validate_fingerprint
from afre.lineage import FeatureLineage, Scalar
from afre.schema import Artifact, contract, enum, require


@enum
class FeatureSemantic(Enum):
    MARKET = "market"
    FUNDAMENTAL = "fundamental"
    EVENT = "event"
    CONTEXT = "context"
    OPTIONS = "options"
    MICROSTRUCTURE = "microstructure"


@enum
class ValueType(Enum):
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    TEXT = "text"


@enum
class FeatureScope(Enum):
    INSTRUMENT = "instrument"
    ENTITY = "entity"


@enum
class AvailabilityRule(Enum):
    SOURCE_PUBLICATION = "source_publication"
    COMPUTED = "computed"


@enum
class MissingPolicy(Enum):
    REJECT = "reject"
    EXPLICIT_STATE = "explicit_state"


@enum
class MissingState(Enum):
    PRESENT = "present"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    NOT_AVAILABLE_YET = "not_available_yet"
    STALE = "stale"
    INVALID = "invalid"
    UNKNOWN = "unknown"


@enum
class DataQuality(Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    INVALID = "invalid"


@contract("feature_definition")
@dataclass(frozen=True, slots=True)
class FeatureDefinition(Artifact):
    name: str
    version: str
    semantic: FeatureSemantic
    value_type: ValueType
    unit: str
    scope: FeatureScope
    lookback_ns: int
    availability_rule: AvailabilityRule
    missing_policy: MissingPolicy
    transformation_version: str
    dependency_ids: tuple[str, ...] = ()

    def _normalize(self) -> None:
        object.__setattr__(self, "dependency_ids", tuple(sorted(self.dependency_ids)))

    def _validate(self) -> None:
        require(
            len(set(self.dependency_ids)) == len(self.dependency_ids), "duplicate dependencies"
        )
        for dependency in self.dependency_ids:
            validate_fingerprint(dependency, "feature_definition")
        if self.availability_rule is AvailabilityRule.SOURCE_PUBLICATION:
            require(
                not self.dependency_ids, "source feature cannot declare computed dependencies"
            )
        else:
            require(bool(self.dependency_ids), "computed feature requires dependencies")


@contract("feature_set")
@dataclass(frozen=True, slots=True)
class FeatureSet(Artifact):
    definitions: tuple[FeatureDefinition, ...]

    def _normalize(self) -> None:
        self.ordered("definitions", "fingerprint")

    def _validate(self) -> None:
        require(bool(self.definitions), "empty feature set")
        keys = [(item.name, item.version) for item in self.definitions]
        require(len(set(keys)) == len(keys), "conflicting feature name/version")


@contract("feature_value")
@dataclass(frozen=True, slots=True)
class FeatureValue(Artifact):
    definition: FeatureDefinition
    instrument: InstrumentId
    effective_ns: int
    observed_ns: int
    available_ns: int
    value: Scalar | None
    missing_state: MissingState
    source: str
    source_version: str
    quality: DataQuality
    lineage: FeatureLineage

    def _validate(self) -> None:
        require(self.observed_ns <= self.available_ns, "observation after availability")
        require(
            self.available_ns >= self.lineage.availability_floor_ns,
            "derived feature backdated before dependency/computation availability",
        )
        require(
            self.lineage.transformation_version == self.definition.transformation_version,
            "transformation version mismatch",
        )
        require(
            tuple(item.definition_id for item in self.lineage.dependencies)
            == self.definition.dependency_ids,
            "dependency definitions mismatch",
        )
        if self.definition.availability_rule is AvailabilityRule.COMPUTED:
            require(
                self.lineage.computation_available_ns is not None, "missing computation time"
            )
        present = self.missing_state is MissingState.PRESENT
        require(
            present == (self.value is not None), "missing is not zero; absence needs a state"
        )
        if not present:
            require(
                self.definition.missing_policy is MissingPolicy.EXPLICIT_STATE,
                "feature rejects missing values",
            )
        else:
            accepted = {
                ValueType.NUMBER: (int, float),
                ValueType.INTEGER: (int,),
                ValueType.BOOLEAN: (bool,),
                ValueType.TEXT: (str,),
            }
            require(
                type(self.value) in accepted[self.definition.value_type], "feature value type"
            )
            require(self.quality is not DataQuality.INVALID, "invalid value cannot be present")


def validate_feature_availability(feature: FeatureValue, origin: ForecastOrigin) -> None:
    require(feature.instrument == origin.instrument, "feature security mismatch")
    require(feature.available_ns <= origin.availability_cutoff_ns, "future feature unavailable")
