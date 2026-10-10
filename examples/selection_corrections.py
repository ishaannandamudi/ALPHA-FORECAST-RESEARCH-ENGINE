"""Valid native label-source correction: rebuild context, preserve completed selections."""

from dataclasses import replace

from afre.research_datasets import DatasetEngine
from afre.research_datasets.definitions import ResearchDatasetDefinition
from afre.research_datasets.manifests import ResearchDatasetManifest, ResearchInputBuild
from afre.research_datasets.preprocessing import FoldPreprocessingState
from afre.research_datasets.samples import ResearchSelection
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import SplitDefinition
from afre.selection import SearchSpace, SelectionRepository
from afre.statistical_models import ModelEngine, PredictionScope
from afre.statistical_models.definitions import BaselineModelSpec
from afre.target_engine.engine import TargetEngine
from afre.target_engine.market_data import TargetBar, TargetSourceBuild
from afre.target_engine.models import TargetDatasetManifest
from examples.feature_store_demo import clocks


def corrected_validation_space(repo: SelectionRepository, space: SearchSpace) -> SearchSpace:
    # Only supplied synthetic VALIDATION return endpoints change. Each revision
    # retains its predecessor and an explicit source clock; TRAIN endpoints stay fixed.
    for (identity,) in tuple(
        repo._connection.execute("SELECT fingerprint FROM target_bars WHERE end_ns=45")
    ):
        bar = repo.get(TargetBar, identity)
        if bar.predecessor_id is not None:
            continue
        opening = repo._connection.execute(
            "SELECT fingerprint FROM target_bars WHERE end_ns=40 AND instrument_id=?",
            (bar.instrument.fingerprint,),
        ).fetchone()
        start = repo.get(TargetBar, opening[0])
        with repo.transaction():
            repo.put(replace(bar, close=start.close, predecessor_id=bar.fingerprint))
    dataset = repo.get(ResearchDatasetManifest, space.dataset_id)
    build = repo.get(ResearchInputBuild, dataset.input_build_id)
    definition = repo.get(ResearchDatasetDefinition, dataset.definition_id)
    requests = {
        s.request.fingerprint: s.request
        for s in (repo.get(ResearchSelection, i) for i in build.selection_ids)
    }
    targets = {}
    sources = {}
    engine = TargetEngine(repo)
    corrected = []
    validation_times = {
        s.timestamp_ns for s in repo.partition_samples(space.fold_id, Partition.VALIDATION)
    }
    for request in requests.values():
        assert request.target_dataset_id is not None
        old = repo.get(TargetDatasetManifest, request.target_dataset_id)
        if not any(o.timestamp_ns in validation_times for o in old.origins):
            corrected.append(request)
            continue
        if request.target_dataset_id not in targets:
            source = repo.get(TargetSourceBuild, old.source_build_id)
            if old.source_build_id not in sources:
                sources[old.source_build_id] = engine.freeze_source(
                    source.source,
                    source.calendar,
                    100,
                    source.action_stream,
                    source.benchmark_ids,
                )
            targets[request.target_dataset_id] = engine.build_dataset(
                old.name + "-explicit-VALIDATION-correction",
                old.origins,
                old.targets,
                sources[old.source_build_id].fingerprint,
                old.universe,
                clocks(100),
            )
        corrected.append(
            replace(request, target_dataset_id=targets[request.target_dataset_id].fingerprint)
        )
    datasets = DatasetEngine(repo)
    new_dataset = datasets.build_dataset(definition, tuple(corrected), 100, 100)
    fold = repo.resolve_fold(space.fold_id)
    split = datasets.build_split(
        new_dataset.fingerprint, repo.get(SplitDefinition, fold.split_definition_id)
    )
    new_fold = repo.resolve_fold(split.fold_ids[fold.ordinal])
    recipes = []
    for r in space.recipes:
        native = r.native_spec
        assert isinstance(native, BaselineModelSpec)
        states = tuple(
            datasets.fit_preprocessing(
                new_fold.fingerprint, repo.get(FoldPreprocessingState, i).spec
            ).fingerprint
            for i in native.preprocessing_state_ids
        )
        recipes.append(
            replace(
                r,
                native_spec=replace(
                    native, fold_id=new_fold.fingerprint, preprocessing_state_ids=states
                ),
                preprocessing_ids=states,
            )
        )
    samples = tuple(
        s.fingerprint
        for s in repo.partition_samples(new_fold.fingerprint, Partition.VALIDATION)
        if s.target_definition_id == space.target_id
    )
    model = ModelEngine(repo)
    native = recipes[0].native_spec
    assert isinstance(native, BaselineModelSpec)
    run = model.fit_model(native, 40, 40, 40)
    anchor = model.predict_samples(run.artifact_id, samples, PredictionScope.VALIDATION)
    return replace(
        space,
        search_key=space.search_key + "-corrected-validation-source",
        dataset_id=new_dataset.fingerprint,
        fold_id=new_fold.fingerprint,
        recipes=tuple(recipes),
        validation_sample_ids=samples,
        failure_anchor_source_ids=tuple(p.fingerprint for p in anchor),
    )
