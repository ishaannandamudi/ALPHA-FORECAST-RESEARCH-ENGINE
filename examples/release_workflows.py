"""Actual cross-phase correction through TRAIN fit, point output, fusion and service."""

from dataclasses import dataclass, replace
from time import perf_counter

from afre.feature_store.models import FeatureVintage
from afre.research_datasets import DatasetEngine, Partition
from afre.selection import (
    DiscreteDimension,
    NativeCandidateRecipe,
    ResourceBudget,
    SearchSpace,
    SelectionCriterion,
)
from afre.service import AFREService, ServiceRepository, SnapshotPublication, SnapshotPublisher
from afre.statistical_models import (
    BaselineModelSpec,
    FittedModelArtifact,
    ModelEngine,
    ModelFamily,
    PointForecast,
    PredictionScope,
    SolverIdentity,
)
from examples.feature_store_demo import clocks, source_vintage
from examples.fusion_native import fuse_sources
from examples.research_dataset_demo import populate, split_definition
from examples.statistical_baselines_demo import baseline_spec
from examples.universe_demo import SECURITIES


@dataclass(frozen=True)
class CorrectionEvidence:
    original_feature: str
    corrected_feature: str
    original_forecast: str
    corrected_forecast: str
    original_fusion: str
    corrected_fusion: str
    original_snapshot: str
    corrected_snapshot: str
    original_model_audit: str
    corrected_model_audit: str
    timings: tuple[tuple[str, float], ...]


def correction_workflow(repo: ServiceRepository, reverse: bool = False) -> CorrectionEvidence:
    timings: dict[str, float] = {}
    start = perf_counter()
    fixture = populate(repo, reverse=reverse)
    timings["fixture_construction"] = perf_counter() - start
    research, models = DatasetEngine(repo), ModelEngine(repo)
    publisher, service = SnapshotPublisher(repo), AFREService(repo)

    def fit_predict(tag: str) -> str:
        start = perf_counter()
        dataset = research.build_dataset(fixture.definition, fixture.requests, 100, 100)
        timings[tag + "_dataset_admission"] = perf_counter() - start
        timings.update(
            (tag + "_" + key, val) for key, val in research.last_build_timings.items()
        )
        split = research.build_split(dataset.fingerprint, split_definition(fixture))
        state = research.fit_preprocessing(split.fold_ids[0], fixture.preprocessing)
        spec = baseline_spec(fixture, split, state, ModelFamily.LINEAR_REGRESSION)
        run = models.fit_model(spec, 40, 40, 40)
        timings.update((tag + "_" + key, val) for key, val in models.last_fit_timings.items())
        samples = tuple(
            s.fingerprint
            for s in repo.partition_samples(split.fold_ids[0], Partition.VALIDATION)
            if s.target_definition_id == spec.target.fingerprint
        )
        return models.predict_samples(run.artifact_id, samples, PredictionScope.VALIDATION)[
            0
        ].fingerprint

    original = fit_predict("original")
    original_audit = models.prediction_audit(original)
    fused = fuse_sources(repo, "release-original", (original,))
    snapshot = publisher.publish(SnapshotPublication(fused, "original", 120))
    frozen = service.get_snapshot(snapshot.snapshot_id)
    old = source_vintage(
        fixture.preprocessing.normalization.feature,
        10,
        10,
        10.0,
        entity=SECURITIES[0].instrument,
    )
    assert repo.get(FeatureVintage, old.fingerprint) == old
    correction = replace(old, value=999.0, clocks=clocks(10), predecessor_id=old.fingerprint)
    with repo.transaction():
        repo.put(correction)
    updated = fit_predict("corrected")
    new_fused = fuse_sources(repo, "release-corrected", (updated,))
    new_snapshot = publisher.publish(SnapshotPublication(new_fused, "corrected", 120))
    assert original != updated and fused != new_fused
    assert snapshot.snapshot_id != new_snapshot.snapshot_id
    assert service.get_snapshot(snapshot.snapshot_id) == frozen
    assert repo.get(FeatureVintage, old.fingerprint) == old
    assert old.fingerprint in snapshot.lineage.node_ids
    corrected_audit = models.prediction_audit(updated)
    assert correction.fingerprint in corrected_audit.evidence_ids
    assert old.fingerprint in original_audit.evidence_ids
    assert models.prediction_audit(original) == original_audit
    # Service lineage keeps frozen TRAIN models as leaves to avoid reopening response truth.
    # The separate native model audit proves the full corrected TRAIN provenance.
    return CorrectionEvidence(
        old.fingerprint,
        correction.fingerprint,
        original,
        updated,
        fused,
        new_fused,
        snapshot.snapshot_id,
        new_snapshot.snapshot_id,
        original_audit.fingerprint,
        corrected_audit.fingerprint,
        tuple(sorted(timings.items())),
    )


def selection_from_native(repo: ServiceRepository, point_ids: tuple[str, ...]) -> "SearchSpace":
    """Declare a finite selection pool on existing native folds, without repopulating inputs."""
    first = repo.get(PointForecast, point_ids[0])
    model = repo.get(FittedModelArtifact, first.model_artifact_id)
    spec = repo.get(BaselineModelSpec, model.spec_id)
    fold = repo.resolve_fold(spec.fold_id)
    specs = (
        spec,
        replace(
            spec,
            family=ModelFamily.UNCONDITIONAL_MEAN,
            solver=SolverIdentity.REFERENCE_STATISTIC,
            l1_penalty=0.0,
            l2_penalty=0.0,
            reference_value=None,
        ),
    )
    samples = tuple(
        s.fingerprint
        for s in repo.partition_samples(spec.fold_id, Partition.VALIDATION)
        if s.target_definition_id == spec.target.fingerprint
    )
    anchors = tuple(
        p.fingerprint
        for p in ModelEngine(repo).predict_samples(
            model.fingerprint, samples, PredictionScope.VALIDATION
        )
    )
    recipes = tuple(
        NativeCandidateRecipe(
            s, (("family", s.family.value),), preprocessing_ids=s.preprocessing_state_ids
        )
        for s in specs
    )
    return SearchSpace(
        "release-native-selection",
        spec.target.fingerprint,
        spec.target.horizon.fingerprint,
        fold.dataset_id,
        fold.fingerprint,
        (DiscreteDimension("family", tuple(s.family.value for s in specs)),),
        recipes,
        ResourceBudget(128, 4096, 256000, 256000, 100000000, 8388608),
        SelectionCriterion.MIN_MSE,
        samples,
        fold.training_cutoff_ns,
        permit_single_valid=True,
        failure_anchor_source_ids=anchors,
    )
