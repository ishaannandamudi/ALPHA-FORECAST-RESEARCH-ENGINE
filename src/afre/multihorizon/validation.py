"""Semantic replay for immutable multi-horizon outputs."""

from typing import TYPE_CHECKING

from afre.multihorizon.alignment import training_context
from afre.multihorizon.artifacts import (
    ConsistencyAudit,
    CovarianceArtifact,
    MultiHorizonEvaluation,
    MultiHorizonFitRun,
    MultiHorizonForecast,
    MultiHorizonLineageAudit,
    SharedParameters,
    SharedPointForecast,
)
from afre.multihorizon.consistency import consistency_for
from afre.multihorizon.definitions import MultiHorizonModelSpec
from afre.multihorizon.dependence import covariance_for
from afre.multihorizon.evaluation import evaluation_for
from afre.multihorizon.forecasts import bundle_for, shared_point_for
from afre.multihorizon.training import fit_for
from afre.schema import Artifact, require
from afre.statistical_models.artifacts import PointForecast

if TYPE_CHECKING:
    from afre.multihorizon.repository import MultiHorizonRepository


def validate_links(repo: "MultiHorizonRepository", value: Artifact) -> None:
    if isinstance(value, MultiHorizonModelSpec):
        training_context(repo, value)
    elif isinstance(value, MultiHorizonFitRun):
        spec = repo.resolve(MultiHorizonModelSpec, value.spec_id)
        run, _ = fit_for(
            repo, spec, value.fit_started_ns, value.fit_completed_ns, value.available_ns
        )
        require(value == run, "multi-horizon TRAIN intersection/run contamination")
        if value.shared_parameters_id:
            repo._validate_links(repo.resolve(SharedParameters, value.shared_parameters_id))
    elif isinstance(value, SharedParameters):
        spec = repo.resolve(MultiHorizonModelSpec, value.spec_id)
        _, expected = fit_for(
            repo, spec, value.available_ns, value.available_ns, value.available_ns
        )
        require(value == expected, "shared parameter contamination")
    elif isinstance(value, CovarianceArtifact):
        run = repo.resolve(MultiHorizonFitRun, value.fit_run_id)
        require(
            value
            == covariance_for(
                repo,
                run,
                value.cutoff_ns,
                value.available_ns,
                value.denominator,
                value.tolerance,
            ),
            "covariance TRAIN/centering contamination",
        )
    elif isinstance(value, SharedPointForecast):
        run = repo.resolve(MultiHorizonFitRun, value.fit_run_id)
        scaffold = repo.resolve(PointForecast, value.scaffold_forecast_id)
        require(
            value == shared_point_for(repo, run, scaffold, value.computed_ns),
            "shared prediction mismatch",
        )
    elif isinstance(value, MultiHorizonForecast):
        run = repo.resolve(MultiHorizonFitRun, value.fit_run_id)
        require(
            value
            == bundle_for(
                repo, run, value.origin, value.entries, value.computed_ns, value.covariance_id
            ),
            "multi-horizon bundle mismatch",
        )
    elif isinstance(value, ConsistencyAudit):
        bundle = repo.resolve(MultiHorizonForecast, value.bundle_id)
        require(value == consistency_for(repo, bundle), "consistency audit mismatch")
    elif isinstance(value, MultiHorizonEvaluation):
        identities = tuple(
            "replay-test" if h.test_evaluation_id else None for h in value.horizons
        )
        require(
            value
            == evaluation_for(
                repo,
                value.bundle_ids,
                value.cutoff_ns,
                value.available_ns,
                identities,
                True,
                value.horizons,
            ),
            "multi-horizon evaluation mismatch",
        )
        for h in value.horizons:
            for identity in (
                h.point_evaluation_id,
                h.probability_evaluation_id,
                h.calibration_evaluation_id,
            ):
                if identity:
                    repo._validate_links(repo.get_any(identity))
    elif isinstance(value, MultiHorizonLineageAudit):
        from afre.multihorizon.lineage import lineage_audit

        require(value == lineage_audit(repo, value.root_id), "multi-horizon lineage mismatch")
