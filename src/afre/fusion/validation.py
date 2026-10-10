"""Fail-closed canonical, relational and numerical replay of fusion artifacts."""

from typing import TYPE_CHECKING

from afre.fusion.accounting import FusionTrialPool
from afre.fusion.application import forecast_for
from afre.fusion.artifacts import (
    FrozenFusionTestChoice,
    FusedForecast,
    FusionArtifact,
    FusionObservation,
)
from afre.fusion.compatibility import admit_spec
from afre.fusion.contributions import stability_for
from afre.fusion.definitions import FusionSourceReference, FusionSpec
from afre.fusion.diagnostics import DiversityMatrix, FusionComparison, FusionWeightStability
from afre.fusion.diversity import diversity_for
from afre.fusion.evaluation import comparison_for
from afre.fusion.external import ExternalFusionDefinition, ExternalFusionOutput
from afre.fusion.learned import fit_for, fitted_values, frozen_inputs
from afre.fusion.lineage import FusionAudit, audit_for
from afre.fusion.metadata import FusionMetadata, validate_metadata
from afre.fusion.sources import observation_for, reference_for
from afre.multiple_testing.families import HypothesisFamily
from afre.multiple_testing.trials import TrialSpecification
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import FoldDefinition
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository


def validate_fusion(repo: "FusionRepository", value: Artifact) -> None:
    if isinstance(value, FusionMetadata):
        validate_metadata(repo, value)
    elif isinstance(value, FusionSourceReference):
        with repo.feature_only():
            require(
                value == reference_for(repo, value.anchor_output_id, value.kind),
                "fusion source reference replay",
            )
    elif isinstance(value, FusionSpec):
        with repo.feature_only():
            admit_spec(repo, value)
    elif isinstance(value, FusionObservation):
        with repo.feature_only():
            ref = repo.resolve(FusionSourceReference, value.source_id)
            require(
                value == observation_for(repo, ref, value.output_id, value.approved_attestors),
                "fusion observation source/value/availability replay",
            )
    elif isinstance(value, FusionArtifact):
        spec = repo.resolve(FusionSpec, value.spec_id)
        if repo._feature_only_depth:
            frozen_inputs(repo, spec, value)
            expected = fitted_values(
                spec, value.rows, value.fit_cutoff_ns, value.computed_ns, value.available_ns
            )
        else:
            expected = fit_for(
                repo,
                spec,
                tuple((r.sample_id, r.observation_ids) for r in value.rows),
                value.fit_cutoff_ns,
                value.computed_ns,
                value.available_ns,
            )
        require(value == expected, "fusion fitted weights/TRAIN/numerical replay")
    elif isinstance(value, FusedForecast):
        with repo.feature_only():
            require(
                value
                == forecast_for(
                    repo,
                    value.artifact_id,
                    value.sample_id,
                    value.observation_ids,
                    value.computed_ns,
                    value.fallback_observation_id,
                ),
                "fused forecast immutable semantic replay",
            )
    elif isinstance(value, ExternalFusionDefinition):
        repo.get_any(value.source.fingerprint)
        repo.get_any(value.target.fingerprint)
    elif isinstance(value, ExternalFusionOutput):
        definition = repo.resolve(ExternalFusionDefinition, value.definition_id)
        require(
            value.clocks.historical_delivery is None
            or value.clocks.historical_delivery.source_id == definition.source.fingerprint,
            "external reconstruction exact source",
        )
    elif isinstance(value, DiversityMatrix):
        require(
            value
            == diversity_for(
                repo,
                value.source_ids,
                value.observation_ids,
                value.available_ns,
                value.cutoff_ns,
            ),
            "fusion diversity semantic replay",
        )
    elif isinstance(value, FusionComparison):
        require(
            value
            == comparison_for(
                repo,
                value.forecast_ids,
                value.cutoff_ns,
                value.available_ns,
                value.test_choice_id,
                value.test_evaluation_id,
                value.trial_pool_id,
            ),
            "fusion comparison semantic replay",
        )
    elif isinstance(value, FrozenFusionTestChoice):
        artifact = repo.resolve(FusionArtifact, value.artifact_id)
        spec = repo.get(FusionSpec, artifact.spec_id)
        test_origins = tuple(
            s.timestamp_ns for s in repo.partition_samples(spec.fold_id, Partition.TEST)
        )
        require(bool(test_origins), "TEST choice requires declared held-out geometry")
        require(
            artifact.available_ns <= value.declared_ns < min(test_origins)
            and value.declared_ns <= repo.get(FoldDefinition, spec.fold_id).training_cutoff_ns,
            "TEST artifact frozen and explicitly chosen before held-out outcomes",
        )
    elif isinstance(value, FusionTrialPool):
        plans = tuple(repo.resolve(TrialSpecification, i) for i in value.plan_ids)
        family = repo.resolve(HypothesisFamily, value.family_id)
        require(
            set(family.plan_ids) == set(value.plan_ids)
            and {dict(p.choices)["fusion-spec"] for p in plans} == set(value.spec_ids)
            and {
                dict(p.choices)["fusion-spec"]
                for p in plans
                if dict(p.choices)["failed-protocol-anchor"] == "True"
            }
            == set(value.failed_spec_ids),
            "fusion complete AFRE19 opportunity accounting",
        )
    elif isinstance(value, FusionWeightStability):
        require(
            value == stability_for(repo, value.artifact_ids), "fusion weight stability replay"
        )
    elif isinstance(value, FusionAudit):
        require(value == audit_for(repo, value.root_id), "fusion audit replay")
