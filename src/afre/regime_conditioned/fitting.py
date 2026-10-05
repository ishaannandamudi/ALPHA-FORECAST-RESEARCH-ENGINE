"""Exact admitted TRAIN state means and explicitly in-sample fitted residuals."""

from math import fsum
from typing import TYPE_CHECKING

from afre.multihorizon.alignment import completed_fit
from afre.regime_conditioned.artifacts import (
    RegimeConditionedModel,
    RegimeConditionedSample,
    RegimeStateFit,
)
from afre.regime_conditioned.definitions import RegimeConditioningSpec
from afre.regime_conditioned.matching import base_context
from afre.regime_conditioned.memberships import effective_support
from afre.regime_conditioned.regimes import RegimeTaxonomy
from afre.regime_conditioned.schema import RegimeModelFamily
from afre.schema import require
from afre.statistical_models.artifacts import DesignMatrix, FittedModelArtifact, ModelFitInputs
from afre.statistical_models.linear_algebra import dot, finite
from afre.statistical_models.schema import PredictionScope

if TYPE_CHECKING:
    from afre.regime_conditioned.repository import RegimeRepository


def fit_for(
    repo: "RegimeRepository",
    spec: RegimeConditioningSpec,
    ids: tuple[str, ...],
    started_ns: int,
    completed_ns: int,
    available_ns: int,
) -> RegimeConditionedModel:
    require(
        0 < len(ids) <= repo.regime_bounds.samples and len(set(ids)) == len(ids),
        "regime TRAIN count bound/duplicates",
    )
    base_context(repo, spec)
    baseline = repo.resolve(FittedModelArtifact, spec.base_model_id)
    completed_fit(repo, "m_fits", "artifact_id", baseline.fingerprint)
    repo._validate_links(baseline)
    inputs = repo.resolve(ModelFitInputs, baseline.fit_inputs_id)
    matrix = repo.resolve(DesignMatrix, inputs.matrix_id)
    rows = {r.sample_id: r for r in matrix.rows}
    observations = tuple(repo.resolve(RegimeConditionedSample, i) for i in sorted(ids))
    require(
        len({o.sample_id for o in observations}) == len(observations),
        "duplicate regime TRAIN sample",
    )
    for o in observations:
        require(
            o.spec_id == spec.fingerprint
            and o.scope is PredictionScope.IN_SAMPLE
            and o.sample_id in rows,
            "regime fit only exact admitted TRAIN",
        )
        repo._validate_links(o)
        row = rows[o.sample_id]
        require(
            o.target_id == row.target_id
            and o.origin == row.origin
            and o.target_available_ns is not None
            and o.target_available_ns <= inputs.training_cutoff_ns
            and row.data_available_ns <= inputs.training_cutoff_ns,
            "regime TRAIN target cutoff",
        )
    admitted = tuple(
        sorted((o for o in observations if o.membership is not None), key=lambda o: o.sample_id)
    )
    require(len(admitted) >= spec.minimum_samples, "insufficient regime TRAIN samples")
    require(
        started_ns >= max(inputs.training_cutoff_ns, baseline.available_ns),
        "regime fit before baseline/cutoff",
    )
    residuals = tuple(
        finite(
            rows[o.sample_id].response
            - baseline.intercept
            - dot(rows[o.sample_id].values, baseline.coefficients)
        )
        for o in admitted
    )
    responses = tuple(rows[o.sample_id].response for o in admitted)
    values = responses if spec.family is RegimeModelFamily.REGIME_TARGET_MEAN else residuals
    taxonomy = repo.resolve(RegimeTaxonomy, spec.taxonomy_id)
    fits = []
    for index, state in enumerate(taxonomy.states):
        peers = [
            (o.sample_id, o.membership.weights[index], value)
            for o, value in zip(admitted, values, strict=True)
            if o.membership is not None and o.membership.weights[index] > 0
        ]
        weights = tuple(w for _, w, _ in peers)
        total, support = fsum(weights), effective_support(weights)
        sufficient = (
            len(peers) >= spec.minimum_state_samples
            and support >= spec.minimum_effective_support
        )
        fits.append(
            RegimeStateFit(
                state,
                tuple(s for s, _, _ in peers),
                weights,
                len(peers),
                total,
                support,
                finite(fsum(w * y for _, w, y in peers) / total) if sufficient else None,
                "available" if sufficient else "insufficient-data",
            )
        )
    return RegimeConditionedModel(
        spec.fingerprint,
        matrix.fingerprint,
        ids,
        tuple(o.fingerprint for o in observations if o.membership is None),
        tuple(fits),
        finite(fsum(residuals) / len(residuals)),
        len(admitted),
        inputs.training_cutoff_ns,
        started_ns,
        completed_ns,
        available_ns,
    )
