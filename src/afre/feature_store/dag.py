"""Immutable DAG specifications with deterministic ordering and static transforms."""

import heapq
import json
from dataclasses import dataclass
from enum import Enum

from afre.feature_store.models import RegisteredFeatureDefinition
from afre.features import AvailabilityRule, ValueType
from afre.hashing import bytes_digest
from afre.ids import validate_fingerprint
from afre.lineage import Parameter
from afre.schema import Artifact, contract, enum, require
from afre.serialization import canonical_json


@enum
class Transformation(Enum):
    IDENTITY = "identity"
    DIFFERENCE = "difference"
    PERCENT_CHANGE = "percent_change"
    LOG_RETURN = "log_return"
    ROLLING_MEAN = "rolling_mean"
    ROLLING_STDDEV = "rolling_stddev"
    STANDARDIZE = "z_score_with_supplied_stats"


@enum
class WindowBasis(Enum):
    LATEST_VALUES = "latest_values"
    ELAPSED_LOOKBACK = "elapsed_lookback"
    OBSERVATION_COUNT = "observation_count"


@enum
class MissingInputPolicy(Enum):
    REJECT = "reject"
    PROPAGATE = "propagate"


@contract("fs_computation_spec")
@dataclass(frozen=True, slots=True)
class FeatureComputationSpec(Artifact):
    output: RegisteredFeatureDefinition
    inputs: tuple[RegisteredFeatureDefinition, ...]
    transformation: Transformation
    transformation_version: str
    implementation_version: str
    minimum_observations: int
    missing_input_policy: MissingInputPolicy
    window_basis: WindowBasis = WindowBasis.LATEST_VALUES
    observation_count: int | None = None
    parameters: tuple[Parameter, ...] = ()
    normalization_state_id: str | None = None

    @property
    def logic_id(self) -> str:
        """Immutable definition logic; supplied learned-state revisions stay independent."""
        fields = json.loads(canonical_json(self))["artifact"]["fields"]
        fields.pop("normalization_state_id")
        return bytes_digest(
            b"AFRE\x00fs-computation-logic\x001.0\x00"
            + json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
        )

    def _normalize(self) -> None:
        # Input order is semantic for binary transforms. Persist it explicitly.
        self.ordered("parameters", "name")

    def _validate(self) -> None:
        require(
            self.output.definition.availability_rule is AvailabilityRule.COMPUTED,
            "computation output must declare computed availability",
        )
        identities = tuple(item.definition.fingerprint for item in self.inputs)
        require(
            tuple(sorted(identities)) == self.output.definition.dependency_ids,
            "computation inputs/output dependencies disagree",
        )
        require(self.output.definition.fingerprint not in identities, "self dependency")
        require(
            all(
                item.scope == self.output.scope
                and item.calendar_id == self.output.calendar_id
                and item.adjustment == self.output.adjustment
                for item in self.inputs
            ),
            "incompatible computation scope/calendar/adjustment",
        )
        require(
            self.parameters == self.output.parameters,
            "definition/computation parameters disagree",
        )
        require(
            self.transformation_version == self.output.definition.transformation_version,
            "transformation version mismatch",
        )
        require(self.minimum_observations > 0, "positive minimum history required")
        if self.window_basis is WindowBasis.OBSERVATION_COUNT:
            require(
                self.observation_count is not None and self.observation_count > 0,
                "observation-count window needs positive count",
            )
        else:
            require(self.observation_count is None, "unexpected observation count")
        rolling = self.transformation in (
            Transformation.ROLLING_MEAN,
            Transformation.ROLLING_STDDEV,
            Transformation.PERCENT_CHANGE,
            Transformation.LOG_RETURN,
        )
        if self.window_basis is not WindowBasis.LATEST_VALUES:
            require(
                len(self.inputs) == 1 and rolling, "window transform requires one history input"
            )
            require(
                self.output.definition.lookback_ns > 0, "explicit positive lookback required"
            )
        if self.transformation in (Transformation.DIFFERENCE,):
            require(
                len(self.inputs) == 2 and self.window_basis is WindowBasis.LATEST_VALUES,
                "difference requires two ordered latest inputs",
            )
        elif self.transformation in (Transformation.IDENTITY, Transformation.STANDARDIZE):
            require(len(self.inputs) == 1, "unary transformation requires one input")
        else:
            require(
                self.window_basis is not WindowBasis.LATEST_VALUES,
                "return/rolling transforms require an explicit history window",
            )
        if self.transformation is not Transformation.IDENTITY:
            require(
                self.output.definition.value_type is ValueType.NUMBER
                and all(
                    item.definition.value_type in (ValueType.NUMBER, ValueType.INTEGER)
                    for item in self.inputs
                ),
                "numeric transformation requires numeric units/types",
            )
        if self.transformation in (
            Transformation.DIFFERENCE,
            Transformation.ROLLING_MEAN,
            Transformation.ROLLING_STDDEV,
            Transformation.IDENTITY,
        ):
            require(
                all(
                    item.definition.unit == self.output.definition.unit for item in self.inputs
                ),
                "implicit unit conversion forbidden",
            )
        else:
            require(self.output.definition.unit == "ratio", "return/z-score unit must be ratio")
        if self.normalization_state_id is not None:
            validate_fingerprint(self.normalization_state_id, "fs_normalization_state")
        require(
            (self.normalization_state_id is not None)
            == (self.transformation is Transformation.STANDARDIZE),
            "normalization state mismatch",
        )


@contract("fs_computation_graph")
@dataclass(frozen=True, slots=True)
class FeatureComputationGraph(Artifact):
    nodes: tuple[RegisteredFeatureDefinition, ...]

    def _normalize(self) -> None:
        self.ordered("nodes", "fingerprint")

    def _validate(self) -> None:
        require(0 < len(self.nodes) <= 256, "graph node bounds exceeded")
        self.topological_order()

    def topological_order(self) -> tuple[str, ...]:
        nodes = {item.definition.fingerprint: item for item in self.nodes}
        require(len(nodes) == len(self.nodes), "duplicate foundation definition in graph")
        degree: dict[str, int] = {}
        children: dict[str, list[str]] = {identity: [] for identity in nodes}
        for identity, node in nodes.items():
            degree[identity] = len(node.definition.dependency_ids)
            for dependency in node.definition.dependency_ids:
                require(
                    dependency in nodes and dependency != identity, "unknown/self dependency"
                )
                require(
                    nodes[dependency].scope == node.scope, "unsupported cross-scope DAG edge"
                )
                children[dependency].append(identity)
        ready = [identity for identity, count in degree.items() if count == 0]
        heapq.heapify(ready)
        ordered: list[str] = []
        while ready:
            identity = heapq.heappop(ready)
            ordered.append(nodes[identity].fingerprint)
            for child in sorted(children[identity]):
                degree[child] -= 1
                if degree[child] == 0:
                    heapq.heappush(ready, child)
        require(len(ordered) == len(nodes), "feature DAG contains a cycle")
        return tuple(ordered)
