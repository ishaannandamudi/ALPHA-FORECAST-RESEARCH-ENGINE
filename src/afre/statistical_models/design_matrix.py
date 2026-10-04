"""Exact numeric TRAIN matrix; held-out responses never enter fitting inputs."""

from typing import TYPE_CHECKING

from afre.feature_store.materialization import PointInTimeJoinResult
from afre.feature_store.normalization import NormalizationMethod
from afre.features import DataQuality, MissingState
from afre.research_datasets.definitions import ResearchDatasetDefinition
from afre.research_datasets.preprocessing import FoldPreprocessingState, apply_state
from afre.research_datasets.schema import ColumnRole, DatasetMissingPolicy, Partition
from afre.research_datasets.splits import FoldDefinition, ResearchSplit
from afre.research_datasets.validation import validate_links as validate_research
from afre.schema import require
from afre.statistical_models.artifacts import DesignMatrix, MatrixExclusion, TrainingMatrixRow
from afre.statistical_models.definitions import PENALIZED_FAMILIES, BaselineModelSpec
from afre.statistical_models.linear_algebra import finite
from afre.statistical_models.schema import ModelFamily, TrainingMissingPolicy
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.statistical_models.repository import ModelRepository


def model_context(
    repo: "ModelRepository", spec: BaselineModelSpec
) -> tuple[FoldDefinition, ResearchSplit, tuple[str, ...]]:
    fold = repo.resolve(FoldDefinition, spec.fold_id)
    dataset = repo.resolve_dataset(fold.dataset_id)
    definition = repo.resolve(ResearchDatasetDefinition, dataset.definition_id)
    require(
        spec.feature_set == definition.feature_set
        and spec.target in definition.target_set.definitions,
        "model/dataset feature or target mismatch",
    )
    if definition.missing_policy is DatasetMissingPolicy.FAIL:
        require(
            spec.missing_policy is TrainingMissingPolicy.FAIL,
            "dataset FAIL requires model FAIL",
        )
    columns = tuple(
        c.definition_id for c in dataset.columns.columns if c.role is ColumnRole.FEATURE
    )
    require(all(c is not None for c in columns), "feature column identity missing")
    feature_ids = tuple(c for c in columns if c is not None)
    require(
        set(feature_ids) == {f.definition.fingerprint for f in spec.feature_set.definitions},
        "design matrix exact feature columns mismatch",
    )
    rows = repo._connection.execute(
        "SELECT split_id FROM r_split_folds WHERE fold_id=?", (spec.fold_id,)
    ).fetchall()
    require(len(rows) == 1, "model requires one exact persisted research split")
    split = repo.resolve(ResearchSplit, rows[0][0])
    require(
        spec.fold_id in split.fold_ids and split.dataset_id == fold.dataset_id,
        "model split/fold mismatch",
    )
    return fold, split, feature_ids


def preprocessing_states(
    repo: "ModelRepository", spec: BaselineModelSpec, validate: bool
) -> tuple[FoldPreprocessingState, ...]:
    states = tuple(
        repo.resolve(FoldPreprocessingState, identity)
        for identity in spec.preprocessing_state_ids
    )
    ids = [s.spec.normalization.feature.definition.fingerprint for s in states]
    require(len(set(ids)) == len(ids), "multiple preprocessing states for one feature")
    required = {f.definition.fingerprint for f in spec.feature_set.definitions}
    require(
        set(ids) <= required and all(s.fold_id == spec.fold_id for s in states),
        "model preprocessing feature/fold mismatch",
    )
    if spec.family in PENALIZED_FAMILIES:
        require(
            set(ids) == required,
            "regularized model requires explicit preprocessing for every feature",
        )
    if spec.family is ModelFamily.PERSISTENCE:
        require(
            all(s.spec.normalization.method is NormalizationMethod.NONE for s in states),
            "persistence reference cannot change return units",
        )
    if validate:
        for state in states:
            validate_research(repo, state)
    return states


def feature_values(
    join: PointInTimeJoinResult,
    feature_ids: tuple[str, ...],
    states: tuple[FoldPreprocessingState, ...],
    application_ns: int,
) -> tuple[tuple[float, ...] | None, int]:
    mapping = {f.definition.fingerprint: f for f in join.row.features}
    require(set(mapping) == set(feature_ids), "prediction/training feature set mismatch")
    transforms = {s.spec.normalization.feature.definition.fingerprint: s for s in states}
    available = max(
        (
            *(f.available_ns for f in mapping.values()),
            *(s.normalization.available_ns for s in states),
        )
    )
    require(available <= application_ns, "feature/preprocessing unavailable at application")
    values = []
    missing = False
    for identity in feature_ids:
        feature = mapping[identity]
        if (
            feature.missing_state is not MissingState.PRESENT
            or feature.quality is not DataQuality.VERIFIED
        ):
            missing = True
            continue
        require(type(feature.value) in (int, float), "non-numeric model feature")
        assert isinstance(feature.value, (int, float))
        value = float(feature.value)
        if identity in transforms:
            transformed = apply_state(transforms[identity], value, application_ns)
            assert transformed is not None
            value = transformed
        values.append(finite(value))
    return (None if missing else tuple(values)), available


def build_matrix(
    repo: "ModelRepository", spec: BaselineModelSpec, transformed_ns: int
) -> DesignMatrix:
    fold, split, columns = model_context(repo, spec)
    states = preprocessing_states(repo, spec, True)
    require(
        all(s.dataset_id == fold.dataset_id for s in states), "preprocessing dataset mismatch"
    )
    samples = repo.partition_samples(spec.fold_id, Partition.TRAIN)
    count = sum(s.target_definition_id == spec.target.fingerprint for s in samples)
    require(
        count <= repo.model_bounds.samples
        and len(columns) <= repo.model_bounds.features
        and count * max(1, len(columns)) <= repo.model_bounds.dense_cells,
        "model matrix sample/feature/dense-cell bound",
    )
    rows, exclusions = [], []
    for sample in samples:
        if sample.target_definition_id != spec.target.fingerprint:
            continue
        require(
            sample.origin is not None
            and sample.join_id is not None
            and sample.target_id is not None,
            "TRAIN sample lacks causal evidence",
        )
        assert (
            sample.origin is not None
            and sample.join_id is not None
            and sample.target_id is not None
        )
        target = repo.resolve(TargetVintage, sample.target_id)
        require(
            target.definition == spec.target
            and target.origin == sample.origin
            and target_known_by_cutoff(target, fold.training_cutoff_ns),
            "future/invalid TRAIN target",
        )
        join = repo.resolve(PointInTimeJoinResult, sample.join_id)
        require(join.row.origin == sample.origin, "matrix feature/sample origin mismatch")
        values, available = feature_values(join, columns, states, transformed_ns)
        if values is None:
            require(
                spec.missing_policy is TrainingMissingPolicy.SKIP,
                "model FAIL encountered missing feature",
            )
            exclusions.append(
                MatrixExclusion(sample.fingerprint, "missing-or-unverified-feature")
            )
            continue
        assert target.value is not None
        rows.append(
            TrainingMatrixRow(
                sample.fingerprint,
                sample.origin,
                sample.join_id,
                sample.feature_vintage_ids,
                values,
                sample.target_id,
                target.value,
                max(available, target.clocks.final_available_ns),
            )
        )
    matrix = DesignMatrix(
        spec.fingerprint,
        fold.dataset_id,
        split.fingerprint,
        spec.fold_id,
        spec.target.fingerprint,
        columns,
        tuple(rows),
        tuple(exclusions),
        spec.preprocessing_state_ids,
        fold.training_cutoff_ns,
        transformed_ns,
    )
    repo.check_model_bounds(matrix)
    return matrix
