"""Offline pipeline timings and a separate 100,000-interval purge profile."""

import cProfile
import io
import json
import pstats
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.research_datasets import (
    DatasetBounds,
    DatasetEngine,
    DatasetRepository,
    Partition,
    ResearchDatasetManifest,
    SampleInformationInterval,
)
from afre.research_datasets.intervals import IntervalIndex
from afre.research_datasets.splitting import embargo_intervals
from examples.research_dataset_demo import populate, split_definition


def run(securities: int = 32, interval_count: int = 100000) -> dict[str, object]:
    timings: dict[str, float] = {}
    with TemporaryDirectory(prefix="afre-research-profile-") as directory:
        path = Path(directory) / "profile.sqlite"
        with DatasetRepository(
            path, DatasetBounds(serialized_bytes=16 * 1024 * 1024)
        ) as repository:
            engine = DatasetEngine(repository)
            start = perf_counter()
            fixture = populate(repository, security_count=securities)
            timings["synthetic_upstream_setup"] = perf_counter() - start
            print("Upstream fixtures ready", file=sys.stderr, flush=True)
            start = perf_counter()
            dataset = engine.build_dataset(fixture.definition, fixture.requests, 100, 100)
            timings["dataset_build_total"] = perf_counter() - start
            timings.update(engine.last_build_timings)
            print("Dataset built", file=sys.stderr, flush=True)
            definition = split_definition(fixture)
            start = perf_counter()
            split = engine.build_split(dataset.fingerprint, definition)
            timings["split_generate_and_persist"] = perf_counter() - start
            folds = engine.folds(split.fingerprint)
            start = perf_counter()
            for fold in folds:
                engine.fit_preprocessing(fold.fingerprint, fixture.preprocessing)
            timings["preprocessing_fit"] = perf_counter() - start
            start = perf_counter()
            partitions = {
                p.value: len(engine.partition_samples(folds[0].fingerprint, p))
                for p in Partition
            }
            timings["partition_retrieval"] = perf_counter() - start
            start = perf_counter()
            with repository.read_snapshot(), repository.validation_cache():
                embargo_intervals(repository, definition, folds)
            timings["embargo_fence_generation"] = perf_counter() - start
            start = perf_counter()
            engine.audit_dataset(dataset.fingerprint)
            engine.audit_fold(folds[0].fingerprint)
            timings["contamination_audits"] = perf_counter() - start
            comparisons = repository.last_interval_comparisons
        start = perf_counter()
        with DatasetRepository(path) as reopened:
            assert reopened.get(ResearchDatasetManifest, dataset.fingerprint) == dataset
            assert DatasetEngine(reopened).folds(split.fingerprint) == folds
        timings["restart_replay"] = perf_counter() - start
        storage = path.stat().st_size
    start = perf_counter()
    # Sparse variable horizons retain interval structure; construction is O(N log N).
    intervals = tuple(
        SampleInformationInterval(i * 10, i * 10 + 4 + i % 3) for i in range(interval_count)
    )
    index = IntervalIndex(intervals)
    hits = sum(
        index.overlaps(SampleInformationInterval(i * 10 + 3, i * 10 + 8))
        for i in range(interval_count)
    )
    timings["large_indexed_purge"] = perf_counter() - start
    assert hits == interval_count and index.comparisons <= interval_count * 2
    return {
        "securities": securities,
        "origins": len(fixture.requests),
        "samples": len(dataset.sample_ids),
        "horizons": len(fixture.definition.target_set.definitions),
        "folds": len(folds),
        "partitions_first_fold": partitions,
        "last_fold_interval_comparisons": comparisons,
        "independent_interval_workload": interval_count,
        "indexed_comparisons": index.comparisons,
        "storage_bytes": storage,
        "declared_serialized_byte_budget": 16 * 1024 * 1024,
        "seconds": {k: round(v, 6) for k, v in timings.items()},
        "scope": "Synthetic pipeline and separate interval scaling; no production SLA",
    }


def main() -> None:
    profile = cProfile.Profile()
    profile.enable()
    result = run()
    profile.disable()
    output = io.StringIO()
    pstats.Stats(profile, stream=output).sort_stats("cumulative").print_stats(20)
    print(json.dumps(result, sort_keys=True, indent=2))
    print(output.getvalue())


if __name__ == "__main__":
    main()
