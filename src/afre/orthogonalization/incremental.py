"""Explicit fixed reference-only and augmented target models, matched TRAIN evidence only."""

from typing import TYPE_CHECKING

from afre.orthogonalization.alignment import rows_for
from afre.orthogonalization.artifacts import ProjectionArtifact
from afre.orthogonalization.definitions import OrthogonalizationSpec
from afre.orthogonalization.evaluation_artifacts import PredictiveModelPair
from afre.orthogonalization.projection import numeric, solve, transform
from afre.research_datasets.samples import ResearchSample
from afre.schema import require
from afre.statistical_models.linear_algebra import dot, finite
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def target_models_for(
    repo: "OrthogonalizationRepository",
    projection_id: str,
    computed_ns: int,
    use_residual: bool,
) -> PredictiveModelPair:
    model = repo.resolve(ProjectionArtifact, projection_id)
    spec = repo.resolve(OrthogonalizationSpec, model.spec_id)
    repo._validate_links(model)
    rows = rows_for(repo, spec.fingerprint, model.row_ids)
    require(computed_ns >= model.available_ns, "target model before projection availability")
    require(len(spec.references) + 2 <= 17, "incremental readout dimension bound")
    targets = []
    for row in rows:
        sample = repo.resolve(ResearchSample, row.sample_id)
        require(sample.target_id is not None, "target model TRAIN truth required")
        assert sample.target_id is not None
        truth = repo.resolve(TargetVintage, sample.target_id)
        require(
            target_known_by_cutoff(truth, spec.cutoff_ns)
            and truth.origin == row.origin
            and truth.definition == spec.target,
            "target model exact known TRAIN truth",
        )
        targets.append(truth)
    y = tuple(numeric(t.value) for t in targets)
    x = tuple(
        transform(tuple(numeric(v) for v in r.references), model.centers, model.scales)
        for r in rows
    )
    candidate = tuple(numeric(r.candidate) for r in rows)
    augmented = tuple(
        (*r, finite(c - model.intercept - dot(r, model.coefficients)) if use_residual else c)
        for r, c in zip(x, candidate, strict=True)
    )
    require(
        len(rows) * (len(spec.references) + 2) ** 2 <= repo.orthogonalization_bounds.cells,
        "target model work bound",
    )
    bi, bc, _, _ = solve(spec, x, y)
    ai, ac, _, _ = solve(spec, augmented, y)
    return PredictiveModelPair(
        model.fingerprint,
        model.row_ids,
        tuple(t.fingerprint for t in targets),
        y,
        bi,
        bc,
        ai,
        ac,
        use_residual,
        spec.cutoff_ns,
        computed_ns,
        computed_ns,
    )
