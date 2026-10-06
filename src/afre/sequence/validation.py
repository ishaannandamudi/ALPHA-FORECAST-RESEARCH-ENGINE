"""Semantic replay at publication/audit; prediction replay remains feature-only."""

from typing import TYPE_CHECKING

from afre.nonlinear.definitions import InteractionDefinition, ScalarFeatureDefinition
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import TestEvaluation
from afre.schema import Artifact, require
from afre.sequence.artifacts import (
    SequenceAudit,
    SequenceCalibrationAssessment,
    SequenceContribution,
    SequenceCoverage,
    SequenceDataset,
    SequenceEvaluation,
    SequenceEvaluationPair,
    SequenceForecast,
    SequenceModelArtifact,
    SequenceObservation,
    SequenceRankEvaluation,
    SequenceRanking,
    SequenceSnapshot,
    SequenceStability,
    SequenceTrainingRow,
    SequenceTransformArtifact,
)
from afre.sequence.definitions import (
    SequenceFeatureDefinition,
    SequenceModelSpec,
    SequenceWindowSpec,
)
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


def validate_sequence(repo: "SequenceRepository", value: Artifact) -> None:
    if isinstance(value, SequenceFeatureDefinition):
        source = repo.get_any(value.source_definition_id)
        require(
            isinstance(source, (ScalarFeatureDefinition, InteractionDefinition))
            and source.unit == value.unit,
            "sequence exact source feature unit",
        )
    elif isinstance(value, SequenceModelSpec):
        require(
            repo.resolve_fold(value.fold_id).training_cutoff_ns == value.cutoff_ns,
            "sequence model exact fold/cutoff",
        )
        require(
            repo.get_any(value.target.fingerprint) == value.target, "sequence target identity"
        )
        for feature in value.features:
            require(
                repo.resolve(SequenceFeatureDefinition, feature.fingerprint) == feature,
                "sequence model persisted features",
            )
        require(
            repo.resolve(SequenceWindowSpec, value.window.fingerprint) == value.window,
            "sequence model persisted window",
        )
    elif isinstance(value, SequenceObservation):
        from afre.sequence.observations import observation_for

        feature = repo.resolve(SequenceFeatureDefinition, value.feature_id)
        require(
            value == observation_for(repo, feature, value.source_id),
            "sequence observation source/time/availability/quality forgery",
        )
    elif isinstance(value, SequenceSnapshot):
        from afre.sequence.windows import snapshot_for

        features = tuple(repo.resolve(SequenceFeatureDefinition, i) for i in value.feature_ids)
        window = repo.resolve(SequenceWindowSpec, value.window_id)
        require(
            value
            == snapshot_for(
                repo, value.origin, features, window, value.candidate_ids, value.computed_ns
            ),
            "sequence cutoff/window/order/mask/encoding forgery",
        )
    elif isinstance(value, SequenceTransformArtifact):
        from afre.sequence.transforms import fit_transform

        spec = repo.resolve(SequenceModelSpec, value.spec_id)
        require(
            value
            == fit_transform(
                repo,
                spec,
                value.train_bindings,
                value.started_ns,
                value.completed_ns,
                value.available_ns,
            ),
            "sequence TRAIN transform forgery",
        )
    elif isinstance(value, SequenceTrainingRow):
        from afre.sequence.datasets import validate_snapshot_input

        spec = repo.resolve(SequenceModelSpec, value.spec_id)
        sample = repo.resolve(ResearchSample, value.sample_id)
        snapshot = repo.resolve(SequenceSnapshot, value.snapshot_id)
        target = repo.resolve(TargetVintage, value.target_id)
        require(
            validate_snapshot_input(repo, spec, sample, snapshot) is Partition.TRAIN
            and sample.target_id == target.fingerprint
            and target.origin == snapshot.origin
            and target.definition == spec.target
            and target_known_by_cutoff(target, spec.cutoff_ns)
            and value.response == target.value
            and value.available_ns
            == max(snapshot.available_ns, target.clocks.final_available_ns),
            "sequence TRAIN row truth forgery",
        )
    elif isinstance(value, SequenceDataset):
        from afre.sequence.datasets import dataset_for

        spec = repo.resolve(SequenceModelSpec, value.spec_id)
        state = repo.resolve(SequenceTransformArtifact, value.transform_id)
        repo._validate_links(state)
        require(
            value == dataset_for(repo, spec, state, value.computed_ns),
            "sequence dataset forgery",
        )
        for row in value.rows:
            require(
                repo.resolve(SequenceTrainingRow, row.fingerprint) == row,
                "sequence row persistence",
            )
    elif isinstance(value, SequenceModelArtifact):
        from afre.sequence.fitting import fit_model

        spec = repo.resolve(SequenceModelSpec, value.spec_id)
        dataset = repo.resolve(SequenceDataset, value.dataset_id)
        repo._validate_links(dataset)
        require(
            value
            == fit_model(
                repo, spec, dataset, value.started_ns, value.completed_ns, value.available_ns
            ),
            "sequence model parameter/loss/clock forgery",
        )
    elif isinstance(value, SequenceContribution):
        repo.resolve(SequenceFeatureDefinition, value.feature_id)
        obs = repo.resolve(SequenceObservation, value.observation_id)
        require(
            obs.feature_id == value.feature_id
            and not obs.missing
            and value.contribution
            == value.transformed_value * value.temporal_weight * value.readout_coefficient,
            "sequence contribution arithmetic/feature forgery",
        )
    elif isinstance(value, SequenceForecast):
        from afre.sequence.predictions import forecast_for

        with repo.feature_only():
            model = repo.resolve(SequenceModelArtifact, value.model_id)
            snapshot = repo.resolve(SequenceSnapshot, value.snapshot_id)
            require(
                value
                == forecast_for(
                    repo,
                    model,
                    value.sample_id,
                    snapshot,
                    value.computed_ns,
                    value.probability.base_forecast_id if value.probability else None,
                ),
                "sequence forecast/contribution/state/law/clock forgery",
            )
    elif isinstance(value, SequenceEvaluationPair):
        forecast = repo.resolve(SequenceForecast, value.forecast_id)
        sample = repo.resolve(ResearchSample, value.sample_id)
        target = repo.resolve(TargetVintage, value.target_id)
        from afre.sequence.evaluation import baseline_value

        require(
            sample.fingerprint == forecast.sample_id
            and sample.target_id == target.fingerprint
            and value.prediction == forecast.value
            and value.truth == target.value
            and value.baseline
            == (
                baseline_value(repo, value.baseline_id, forecast) if value.baseline_id else None
            ),
            "sequence evaluation pair truth/baseline forgery",
        )
    elif isinstance(value, SequenceEvaluation):
        from afre.sequence.evaluation import evaluation_for

        seal = (
            repo.resolve(TestEvaluation, value.test_evaluation_id)
            if value.test_evaluation_id
            else None
        )
        require(
            value
            == evaluation_for(
                repo,
                value.forecast_ids,
                value.cutoff_ns,
                value.available_ns,
                tuple((p.sample_id, p.baseline_id) for p in value.pairs if p.baseline_id),
                seal,
                value.thresholds,
            ),
            "sequence matched evaluation forgery",
        )
    elif isinstance(value, SequenceStability):
        from afre.sequence.diagnostics import stability_for

        require(
            value == stability_for(repo, value.model_ids, value.available_ns),
            "sequence stability forgery",
        )
    elif isinstance(value, SequenceCoverage):
        from afre.sequence.diagnostics import coverage_for

        require(
            value == coverage_for(repo, value.snapshot_ids, value.available_ns),
            "sequence coverage forgery",
        )
    elif isinstance(value, SequenceCalibrationAssessment):
        from afre.sequence.calibration import assessment_for

        require(
            value
            == assessment_for(
                repo,
                value.forecast_id,
                value.observation_ids,
                value.cutoff_ns,
                value.minimum_count,
                value.proposed_state_id,
            ),
            "sequence calibration forgery",
        )
    elif isinstance(value, SequenceRanking):
        from afre.sequence.cross_sectional import ranking_for

        require(
            value == ranking_for(repo, value.ranking_id, value.forecast_ids),
            "sequence rank forgery",
        )
    elif isinstance(value, SequenceRankEvaluation):
        from afre.cross_sectional.artifacts import CrossSectionEvaluation, CrossSectionTruth

        ranking = repo.resolve(SequenceRanking, value.ranking_id)
        matched = repo.resolve(SequenceEvaluation, value.matched_id)
        cross = repo.resolve(CrossSectionEvaluation, value.cross_section_id)
        truth = repo.resolve(CrossSectionTruth, cross.truth_id)
        repo._validate_links(cross)
        repo._validate_links(truth)
        expected = {
            repo.resolve(SequenceForecast, pair.forecast_id).security.fingerprint: (
                pair.target_id,
                pair.truth,
            )
            for pair in matched.pairs
        }
        actual = {
            row.security.fingerprint: (row.target_id, row.value)
            for row in truth.rows
            if row.target_id is not None
        }
        require(
            cross.ranking_id == ranking.ranking_id
            and truth.ranking_id == ranking.ranking_id
            and set(matched.forecast_ids) == set(ranking.forecast_ids)
            and cross.cutoff_ns == truth.cutoff_ns == matched.cutoff_ns
            and cross.available_ns == truth.available_ns == matched.available_ns
            and actual == expected,
            "sequence rank evaluation exact truth/cutoff evidence",
        )
    elif isinstance(value, SequenceAudit):
        from afre.sequence.lineage import lineage_for

        require(value == lineage_for(repo, value.root_id), "sequence lineage forgery")
    else:
        from afre.sequence.lineage import sequence_edges

        for identity in sequence_edges(value):
            repo.get_any(identity)
