"""Fixed typed model choices compose the unchanged foundation ModelSpec."""

from dataclasses import dataclass

from afre.feature_store.models import FeatureSetManifest
from afre.features import FeatureSemantic, FeatureSet, ValueType
from afre.horizons import HorizonBasis
from afre.ids import validate_fingerprint
from afre.lineage import Parameter
from afre.models import ModelSpec, TrainingPolicy
from afre.schema import Artifact, contract, require
from afre.statistical_models.schema import (
    IMPLEMENTATION_VERSION,
    SOLVER_VERSION,
    InterceptPolicy,
    ModelFamily,
    NonconvergencePolicy,
    RankDeficiencyPolicy,
    RowWeighting,
    SolverIdentity,
    TrainingMissingPolicy,
)
from afre.target_engine.definitions import TargetDefinition
from afre.targets import TargetSpec, TargetType

CONSTANT_FAMILIES = (
    ModelFamily.UNCONDITIONAL_MEAN,
    ModelFamily.UNCONDITIONAL_MEDIAN,
    ModelFamily.REFERENCE_VALUE,
    ModelFamily.PERSISTENCE,
)
PENALIZED_FAMILIES = (
    ModelFamily.RIDGE_REGRESSION,
    ModelFamily.LASSO_REGRESSION,
    ModelFamily.ELASTIC_NET,
)


@contract("m_persistence_reference")
@dataclass(frozen=True, slots=True)
class PersistenceReference(Artifact):
    feature_definition_id: str
    target_definition_id: str
    trailing_window_ns: int
    semantic_version: str

    def _validate(self) -> None:
        validate_fingerprint(self.feature_definition_id, "feature_definition")
        validate_fingerprint(self.target_definition_id, "target_definition")
        require(self.trailing_window_ns > 0, "persistence requires a completed trailing window")


@contract("m_spec")
@dataclass(frozen=True, slots=True)
class BaselineModelSpec(Artifact):
    family: ModelFamily
    feature_set: FeatureSetManifest
    target: TargetDefinition
    fold_id: str
    preprocessing_state_ids: tuple[str, ...]
    intercept: InterceptPolicy
    l1_penalty: float
    l2_penalty: float
    regularize_intercept: bool
    max_iterations: int
    tolerance: float
    condition_limit: float
    rank_policy: RankDeficiencyPolicy
    nonconvergence: NonconvergencePolicy
    missing_policy: TrainingMissingPolicy
    random_seed: int
    solver: SolverIdentity
    reference_value: float | None = None
    persistence: PersistenceReference | None = None
    weighting: RowWeighting = RowWeighting.EQUAL_ROWS
    implementation_version: str = IMPLEMENTATION_VERSION
    solver_version: str = SOLVER_VERSION

    def _normalize(self) -> None:
        require(
            len(set(self.preprocessing_state_ids)) == len(self.preprocessing_state_ids),
            "duplicate model preprocessing",
        )
        object.__setattr__(
            self, "preprocessing_state_ids", tuple(sorted(self.preprocessing_state_ids))
        )

    def _validate(self) -> None:
        validate_fingerprint(self.fold_id, "r_fold")
        for identity in self.preprocessing_state_ids:
            validate_fingerprint(identity, "r_preprocessing_state")
        require(0 <= self.random_seed < 2**64, "model seed outside uint64")
        require(self.l1_penalty >= 0 and self.l2_penalty >= 0, "negative regularization")
        require(
            self.max_iterations > 0 and 0 < self.tolerance < 1, "invalid convergence settings"
        )
        require(self.condition_limit >= 1, "invalid QR condition proxy limit")
        require(
            self.intercept is not InterceptPolicy.WITHIN_ORIGIN,
            "within-origin intercept fitting is deferred; declare global or none",
        )
        require(
            self.intercept is not InterceptPolicy.NONE or not self.regularize_intercept,
            "cannot penalize absent intercept",
        )
        require(
            all(
                f.definition.value_type in (ValueType.NUMBER, ValueType.INTEGER)
                for f in self.feature_set.definitions
            ),
            "model features must be numeric",
        )
        require(
            (self.reference_value is not None) == (self.family is ModelFamily.REFERENCE_VALUE),
            "reference baseline requires exactly one supplied value",
        )
        require(
            (self.persistence is not None) == (self.family is ModelFamily.PERSISTENCE),
            "persistence baseline requires exact reference semantics",
        )
        expected_solver = (
            SolverIdentity.REFERENCE_STATISTIC
            if self.family in CONSTANT_FAMILIES
            else SolverIdentity.COORDINATE_DESCENT
            if self.family in (ModelFamily.LASSO_REGRESSION, ModelFamily.ELASTIC_NET)
            else SolverIdentity.PIVOTED_HOUSEHOLDER_QR
        )
        require(self.solver is expected_solver, "model family/solver mismatch")
        require(
            self.family in (ModelFamily.LASSO_REGRESSION, ModelFamily.ELASTIC_NET)
            or self.l1_penalty == 0,
            "family does not support L1 penalty",
        )
        require(
            self.family in (ModelFamily.RIDGE_REGRESSION, ModelFamily.ELASTIC_NET)
            or self.l2_penalty == 0,
            "family does not support L2 penalty",
        )
        if self.family in CONSTANT_FAMILIES:
            require(not self.regularize_intercept, "reference statistics cannot be regularized")
            require(
                self.intercept
                is (
                    InterceptPolicy.NONE
                    if self.family is ModelFamily.PERSISTENCE
                    else InterceptPolicy.GLOBAL
                ),
                "reference statistic/persistence intercept policy mismatch",
            )
        if self.family is ModelFamily.RESIDUAL_LINEAR:
            require(
                self.target.target_type is TargetType.RESIDUAL_RETURN,
                "residual baseline requires supplied AFRE-2 residual target",
            )
        if self.persistence is not None:
            reference = self.persistence
            require(
                self.target.target_type in (TargetType.SIMPLE_RETURN, TargetType.LOG_RETURN)
                and self.target.horizon.basis is HorizonBasis.ELAPSED_TIME,
                "persistence supports only explicit elapsed simple/log return semantics",
            )
            require(
                reference.target_definition_id == self.target.fingerprint
                and reference.trailing_window_ns == self.target.horizon.duration_ns,
                "persistence horizon/target mismatch",
            )
            matching = [
                f
                for f in self.feature_set.definitions
                if f.definition.fingerprint == reference.feature_definition_id
            ]
            require(len(matching) == 1, "persistence reference outside exact feature set")
            feature = matching[0].definition
            require(
                feature.semantic is FeatureSemantic.MARKET
                and feature.unit == "dimensionless"
                and feature.lookback_ns >= reference.trailing_window_ns,
                "persistence requires a declared causal trailing return feature",
            )

    @property
    def foundation_spec(self) -> ModelSpec:
        parameters = (
            Parameter("l1_penalty", self.l1_penalty),
            Parameter("l2_penalty", self.l2_penalty),
            Parameter("intercept", self.intercept.value),
            Parameter("regularize_intercept", self.regularize_intercept),
            Parameter("max_iterations", self.max_iterations),
            Parameter("tolerance", self.tolerance),
            Parameter("condition_limit", self.condition_limit),
            Parameter("solver", self.solver.value),
            Parameter("solver_version", self.solver_version),
            Parameter("rich_model_spec_id", self.fingerprint),
        )
        target = TargetSpec(
            self.target.target_type,
            self.target.horizon,
            "target-value",
            self.target.implementation_version,
            self.target.benchmark.instrument if self.target.benchmark else None,
        )
        policy = TrainingPolicy(
            "train_only",
            "1",
            (
                Parameter("fold_id", self.fold_id),
                Parameter("missing_policy", self.missing_policy.value),
                Parameter("weighting", self.weighting.value),
            ),
        )
        return ModelSpec(
            self.family.value,
            parameters,
            FeatureSet(tuple(f.definition for f in self.feature_set.definitions)),
            target,
            policy,
            self.random_seed,
            self.implementation_version,
        )
