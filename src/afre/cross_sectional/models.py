"""Explicit relative-target model over an admitted AFRE-5 TRAIN matrix."""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from afre.cross_sectional.definitions import origin_context
from afre.cross_sectional.normalization import average
from afre.cross_sectional.schema import TargetCentering
from afre.feature_store.materialization import PointInTimeJoinResult
from afre.ids import validate_fingerprint
from afre.multihorizon.alignment import completed_fit
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import (
    DesignMatrix,
    FitDiagnostics,
    FittedModelArtifact,
    ModelFitInputs,
    PointForecast,
)
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.design_matrix import feature_values, preprocessing_states
from afre.statistical_models.fitting import fit_values
from afre.statistical_models.linear_algebra import dot, finite
from afre.statistical_models.schema import ModelFamily

if TYPE_CHECKING:
    from afre.cross_sectional.repository import CrossSectionRepository


@contract("cs_model_spec")
@dataclass(frozen=True, slots=True)
class CrossSectionModelSpec(Artifact):
    baseline_model_id: str
    target_centering: TargetCentering = TargetCentering.NONE
    minimum_train_peers: int = 2
    loss: str = "individual-squared-error-sum-v1"

    def _validate(self) -> None:
        validate_fingerprint(self.baseline_model_id, "m_artifact")
        require(
            self.minimum_train_peers >= 2 and self.loss == "individual-squared-error-sum-v1",
            "cross-sectional model loss",
        )


@contract("cs_model")
@dataclass(frozen=True, slots=True)
class CrossSectionModel(Artifact):
    spec_id: str
    baseline_model_id: str
    matrix_id: str
    feature_ids: tuple[str, ...]
    coefficients: tuple[float, ...]
    intercept: float
    train_groups: tuple[tuple[str, ...], ...]
    train_centers: tuple[float, ...]
    diagnostics: FitDiagnostics
    cutoff_ns: int
    fit_started_ns: int
    fit_completed_ns: int
    available_ns: int

    def _validate(self) -> None:
        for key, domain in (
            (self.spec_id, "cs_model_spec"),
            (self.baseline_model_id, "m_artifact"),
            (self.matrix_id, "m_matrix"),
        ):
            validate_fingerprint(key, domain)
        require(
            len(self.coefficients) == len(self.feature_ids)
            and len(self.train_groups) == len(self.train_centers),
            "relative model shape",
        )
        require(
            self.cutoff_ns <= self.fit_started_ns <= self.fit_completed_ns <= self.available_ns,
            "relative fit clocks",
        )


@contract("cs_prediction")
@dataclass(frozen=True, slots=True)
class CrossSectionPrediction(Artifact):
    model_id: str
    scaffold_id: str
    value: float
    computed_ns: int
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.model_id, "cs_model")
        validate_fingerprint(self.scaffold_id, "m_point_forecast")
        require(self.available_ns >= self.computed_ns, "relative prediction clocks")


def fit_relative(
    repo: "CrossSectionRepository",
    spec: CrossSectionModelSpec,
    started_ns: int,
    completed_ns: int,
    available_ns: int,
) -> CrossSectionModel:
    baseline = repo.resolve(FittedModelArtifact, spec.baseline_model_id)
    completed_fit(repo, "m_fits", "artifact_id", baseline.fingerprint)
    repo._validate_links(baseline)
    base = repo.resolve(BaselineModelSpec, baseline.spec_id)
    require(
        base.family is ModelFamily.CROSS_SECTIONAL_LINEAR,
        "requires cross-sectional linear baseline",
    )
    inputs = repo.resolve(ModelFitInputs, baseline.fit_inputs_id)
    matrix = repo.resolve(DesignMatrix, inputs.matrix_id)
    require(
        len(matrix.feature_ids) <= repo.cross_section_bounds.features,
        "cross-section feature bound",
    )
    buckets: dict[tuple[int, int, str, str, str], list[int]] = {}
    for i, row in enumerate(matrix.rows):
        buckets.setdefault(origin_context(row.origin), []).append(i)
    require(
        all(len(ids) >= spec.minimum_train_peers for ids in buckets.values()),
        "TRAIN origin has too few admitted peers",
    )
    groups = tuple(
        tuple(matrix.rows[i].sample_id for i in ids) for _, ids in sorted(buckets.items())
    )
    means = tuple(
        average(tuple(matrix.rows[i].response for i in ids))
        if spec.target_centering is TargetCentering.WITHIN_ORIGIN
        else 0.0
        for _, ids in sorted(buckets.items())
    )
    centers = {s: m for ids, m in zip(groups, means, strict=True) for s in ids}
    centered = replace(
        matrix,
        rows=tuple(
            replace(r, response=finite(r.response - centers[r.sample_id])) for r in matrix.rows
        ),
    )
    result = fit_values(base, centered, repo.model_bounds)
    require(
        started_ns >= max(inputs.training_cutoff_ns, baseline.available_ns),
        "relative fit before evidence",
    )
    return CrossSectionModel(
        spec.fingerprint,
        baseline.fingerprint,
        matrix.fingerprint,
        matrix.feature_ids,
        result.coefficients,
        result.intercept,
        groups,
        means,
        result.diagnostics,
        inputs.training_cutoff_ns,
        started_ns,
        completed_ns,
        available_ns,
    )


def relative_prediction(
    repo: "CrossSectionRepository",
    model: CrossSectionModel,
    scaffold: PointForecast,
    computed_ns: int,
) -> CrossSectionPrediction:
    require(
        scaffold.model_artifact_id == model.baseline_model_id
        and scaffold.historical_admissible
        and model.available_ns <= scaffold.input.origin.availability_cutoff_ns
        and computed_ns >= scaffold.available_ns,
        "relative prediction evidence/time",
    )
    repo._validate_links(scaffold)
    baseline = repo.resolve(FittedModelArtifact, model.baseline_model_id)
    base = repo.resolve(BaselineModelSpec, baseline.spec_id)
    join = repo.resolve(PointInTimeJoinResult, scaffold.input.join_id)
    values, _ = feature_values(
        join,
        model.feature_ids,
        preprocessing_states(repo, base, False),
        scaffold.input.origin.availability_cutoff_ns,
    )
    require(values is not None, "relative prediction features missing")
    assert values is not None
    return CrossSectionPrediction(
        model.fingerprint,
        scaffold.fingerprint,
        finite(model.intercept + dot(values, model.coefficients)),
        computed_ns,
        computed_ns,
    )
