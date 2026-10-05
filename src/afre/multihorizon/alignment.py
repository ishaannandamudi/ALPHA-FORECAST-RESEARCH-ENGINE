"""Intersection of existing AFRE-5 TRAIN matrices, keyed by full origin identity."""

from typing import TYPE_CHECKING

from afre.calibration.artifacts import CalibrationState
from afre.multihorizon.artifacts import AlignedTrainRow, HorizonTrainEvidence
from afre.multihorizon.definitions import MultiHorizonModelSpec
from afre.probabilistic.artifacts import ProbabilisticModelArtifact
from afre.probabilistic.definitions import ProbabilisticModelSpec
from afre.schema import require
from afre.statistical_models.artifacts import DesignMatrix, FittedModelArtifact, ModelFitInputs
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.linear_algebra import dot, finite
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.multihorizon.repository import MultiHorizonRepository


def completed_fit(
    repo: "MultiHorizonRepository", table: str, column: str, identity: str
) -> None:
    rows = repo._connection.execute(
        f"SELECT fingerprint FROM {table} WHERE {column}=?", (identity,)
    ).fetchall()
    require(len(rows) == 1, "multi-horizon composition requires one completed fit")
    repo._validate_links(repo.get_any(rows[0][0]))


def training_context(
    repo: "MultiHorizonRepository", spec: MultiHorizonModelSpec
) -> tuple[tuple[HorizonTrainEvidence, ...], tuple[DesignMatrix, ...]]:
    repo.check_multihorizon_bounds(spec)
    evidence, matrices = [], []
    for binding in spec.bindings:
        model = repo.resolve(FittedModelArtifact, binding.point_model_id)
        repo._validate_links(model)
        completed_fit(repo, "m_fits", "artifact_id", model.fingerprint)
        base = repo.resolve(BaselineModelSpec, model.spec_id)
        inputs = repo.resolve(ModelFitInputs, model.fit_inputs_id)
        require(
            base.fingerprint == binding.point_spec_id
            and base.target in spec.horizon_set.targets
            and base.target.fingerprint == binding.target_definition_id
            and base.feature_set.fingerprint == binding.feature_set_id
            and base.fold_id == binding.fold_id == inputs.fold_id
            and inputs.training_cutoff_ns == binding.training_cutoff_ns
            and inputs.preprocessing_state_ids == binding.preprocessing_state_ids,
            "horizon model/feature/fold/cutoff binding mismatch",
        )
        if binding.probability_model_id is not None:
            probability = repo.resolve(ProbabilisticModelArtifact, binding.probability_model_id)
            repo._validate_links(probability)
            completed_fit(repo, "p_fits", "artifact_id", probability.fingerprint)
            ps = repo.resolve(ProbabilisticModelSpec, probability.spec_id)
            require(
                ps.fingerprint == binding.probability_spec_id
                and ps.point_model_id == model.fingerprint
                and ps.target == base.target
                and ps.fold_id == base.fold_id,
                "horizon probability binding mismatch",
            )
        if binding.calibration_state_id is not None:
            state = repo.resolve(CalibrationState, binding.calibration_state_id)
            repo._validate_links(state)
            completed_fit(repo, "c_fits", "state_id", state.fingerprint)
            require(
                state.inputs.spec_id == binding.calibration_spec_id
                and state.inputs.raw_model_id == binding.probability_model_id
                and state.target_definition_id == base.target.fingerprint,
                "horizon calibration binding mismatch",
            )
        matrix = repo.resolve(DesignMatrix, inputs.matrix_id)
        matrices.append(matrix)
        evidence.append(
            HorizonTrainEvidence(
                binding.target_definition_id,
                model.fingerprint,
                matrix.fingerprint,
                inputs.fold_id,
                inputs.training_cutoff_ns,
                inputs.preprocessing_state_ids,
                inputs.train_sample_ids,
            )
        )
    require(
        sum(len(m.rows) for m in matrices) <= repo.multihorizon_bounds.samples,
        "multi-horizon TRAIN sample bound",
    )
    return tuple(evidence), tuple(matrices)


def aligned_rows(
    repo: "MultiHorizonRepository",
    spec: MultiHorizonModelSpec,
    matrices: tuple[DesignMatrix, ...],
    cutoff_ns: int,
) -> tuple[AlignedTrainRow, ...]:
    maps = []
    for matrix in matrices:
        mapping = {}
        for row in matrix.rows:
            target = repo.resolve(TargetVintage, row.target_id)
            if row.origin.timestamp_ns < cutoff_ns and target_known_by_cutoff(
                target, cutoff_ns
            ):
                require(row.origin.fingerprint not in mapping, "duplicate TRAIN origin/horizon")
                mapping[row.origin.fingerprint] = row
        maps.append(mapping)
    keys = set(maps[0]).intersection(*(set(m) for m in maps[1:]))
    require(
        len(keys) * len(maps) <= repo.multihorizon_bounds.work_cells, "intersection work bound"
    )
    models = tuple(repo.resolve(FittedModelArtifact, b.point_model_id) for b in spec.bindings)
    result = []
    for key in keys:
        rows = tuple(m[key] for m in maps)
        require(all(r.origin == rows[0].origin for r in rows), "full origin alignment mismatch")
        result.append(
            AlignedTrainRow(
                rows[0].origin,
                tuple(r.sample_id for r in rows),
                tuple(r.target_id for r in rows),
                tuple(r.response for r in rows),
                tuple(
                    finite(r.response - finite(m.intercept + dot(r.values, m.coefficients)))
                    for r, m in zip(rows, models, strict=True)
                ),
                tuple(r.values for r in rows),
                max(r.data_available_ns for r in rows),
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda r: (
                r.origin.timestamp_ns,
                r.origin.instrument.fingerprint,
                r.origin.fingerprint,
            ),
        )
    )
