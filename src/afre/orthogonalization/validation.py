"""Replay every completed artifact from exact immutable semantic evidence."""

from typing import TYPE_CHECKING

from afre.orthogonalization.artifacts import (
    AlignedSignalRow,
    OrthogonalizationAudit,
    OrthogonalSignalValue,
    ProjectionArtifact,
    RedundancyMatrix,
)
from afre.orthogonalization.definitions import OrthogonalizationSpec, SignalReference
from afre.orthogonalization.evaluation_artifacts import (
    PartialCorrelation,
    PredictiveModelPair,
    RedundancyEvaluation,
    RedundancyStability,
)
from afre.orthogonalization.signals import GenericSignalSource, SignalObservation
from afre.research_datasets.splits import FoldDefinition, TestEvaluation
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.orthogonalization.repository import OrthogonalizationRepository


def validate_orthogonalization(repo: "OrthogonalizationRepository", v: Artifact) -> None:
    if isinstance(v, SignalReference):
        if v.target:
            repo.get_any(v.target.fingerprint)
    elif isinstance(v, GenericSignalSource):
        require(
            repo.resolve(SignalReference, v.reference.fingerprint) == v.reference,
            "generic reference persistence",
        )
        repo.get_any(v.source.fingerprint)
    elif isinstance(v, SignalObservation):
        from afre.orthogonalization.sources import observation_for

        with repo.feature_only():
            require(
                v
                == observation_for(
                    repo,
                    repo.resolve(SignalReference, v.reference_id),
                    v.source_id,
                    v.sample_id,
                    v.approved_attestors,
                ),
                "signal observation source/value/clock forgery",
            )
    elif isinstance(v, OrthogonalizationSpec):
        repo.resolve(FoldDefinition, v.fold_id)
        require(
            all(
                repo.resolve(SignalReference, r.fingerprint) == r
                for r in (v.candidate, *v.references)
            ),
            "projection exact persisted reference definitions",
        )
    elif isinstance(v, AlignedSignalRow):
        from afre.orthogonalization.alignment import row_for

        with repo.feature_only():
            require(
                v
                == row_for(
                    repo, repo.resolve(OrthogonalizationSpec, v.spec_id), v.observation_ids
                ),
                "aligned sample/reference/value forgery",
            )
    elif isinstance(v, RedundancyMatrix):
        from afre.orthogonalization.correlation import matrix_for

        with repo.feature_only():
            require(
                v == matrix_for(repo, v.spec_id, v.row_ids, v.available_ns),
                "redundancy matrix/intersection/metric forgery",
            )
    elif isinstance(v, ProjectionArtifact):
        from afre.orthogonalization.projection import projection_for

        with repo.feature_only():
            require(
                v
                == projection_for(
                    repo,
                    repo.resolve(OrthogonalizationSpec, v.spec_id),
                    v.row_ids,
                    v.matrix_id,
                    v.computed_ns,
                ),
                "projection coefficients/preprocessing/TRAIN/rank/statistics forgery",
            )
    elif isinstance(v, OrthogonalSignalValue):
        from afre.orthogonalization.residualization import residual_for

        with repo.feature_only():
            require(
                v == residual_for(repo, v.projection_id, v.row_id, v.computed_ns),
                "residual source/projection/value/availability forgery",
            )
    elif isinstance(v, PredictiveModelPair):
        from afre.orthogonalization.incremental import target_models_for

        require(
            v
            == target_models_for(
                repo, v.projection_id, v.computed_ns, v.augmented_uses_residual
            ),
            "target model TRAIN evidence/coefficients forgery",
        )
    elif isinstance(v, RedundancyEvaluation):
        from afre.orthogonalization.evaluation import evaluation_for

        seal = (
            repo.resolve(TestEvaluation, v.test_evaluation_id) if v.test_evaluation_id else None
        )
        require(
            v
            == evaluation_for(
                repo,
                v.residual_ids,
                v.cutoff_ns,
                v.available_ns,
                v.predictive_pair_id,
                bool(v.target_ids),
                seal,
            ),
            "heldout redundancy/partial/incremental/truth forgery",
        )
    elif isinstance(v, PartialCorrelation):
        from afre.orthogonalization.partial import partial_for

        require(
            v == partial_for(repo, v.left_residual_ids, v.right_residual_ids, v.available_ns),
            "partial frozen residual association forgery",
        )
    elif isinstance(v, RedundancyStability):
        from afre.orthogonalization.diagnostics import stability_for

        require(
            v == stability_for(repo, v.evaluation_ids, v.available_ns),
            "stability summary forgery",
        )
    elif isinstance(v, OrthogonalizationAudit):
        from afre.orthogonalization.lineage import audit_for

        require(v == audit_for(repo, v.root_id), "orthogonal audit forgery")
