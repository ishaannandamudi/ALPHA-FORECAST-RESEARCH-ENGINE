"""Deterministic fold statistics; horizons do not duplicate feature observations."""

from typing import TYPE_CHECKING

from afre.feature_store.materialization import PointInTimeJoinResult
from afre.feature_store.normalization import NormalizationState
from afre.features import DataQuality, MissingState
from afre.research_datasets.preprocessing import (
    FoldPreprocessingSpec,
    FoldPreprocessingState,
    fit_parameters,
)
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition, PreprocessingScope
from afre.research_datasets.splits import FoldDefinition
from afre.schema import require

if TYPE_CHECKING:
    from afre.research_datasets.repository import DatasetRepository


def preprocessing_for(
    repo: "DatasetRepository",
    fold: FoldDefinition,
    spec: FoldPreprocessingSpec,
    available_ns: int,
) -> FoldPreprocessingState:
    require(
        spec.scope is PreprocessingScope.TRAIN_PARTITION,
        "within-origin/group preprocessing is prepared and deferred",
    )
    require(available_ns >= fold.training_cutoff_ns, "fit availability before training cutoff")
    samples = repo.partition_samples(repo.identity(fold), Partition.TRAIN)
    feature = spec.normalization.feature
    representatives: dict[tuple[int, str], ResearchSample] = {}
    for sample in samples:
        key = (sample.timestamp_ns, sample.security.instrument.fingerprint)
        if key not in representatives or repo.identity(sample) < repo.identity(
            representatives[key]
        ):
            representatives[key] = sample
    fit_ids, skipped_ids, vintage_ids, values = [], [], set(), []
    for _, sample in sorted(representatives.items()):
        assert sample.join_id is not None
        join = repo.resolve(PointInTimeJoinResult, sample.join_id)
        audit = next((a for a in join.audits if a.feature == feature), None)
        require(audit is not None, "preprocessing feature outside dataset feature set")
        assert audit is not None
        selected = audit.selected
        if (
            audit.state is not MissingState.PRESENT
            or selected is None
            or selected.quality is not DataQuality.VERIFIED
        ):
            skipped_ids.append(repo.identity(sample))
        else:
            require(type(selected.value) in (int, float), "non-numeric preprocessing value")
            assert isinstance(selected.value, (int, float))
            fit_ids.append(repo.identity(sample))
            vintage_ids.add(selected.fingerprint)
            values.append(float(selected.value))
    require(bool(values), "no usable TRAIN values for preprocessing")
    # The wrapper retains research observation multiplicity; AFRE-1 pins unique vintages.
    state = NormalizationState(
        spec.normalization,
        tuple(sorted(vintage_ids)),
        fold.training_cutoff_ns,
        available_ns,
        fit_parameters(spec, tuple(values)),
        feature.source_dataset_ids[0],
    )
    return FoldPreprocessingState(
        fold.dataset_id, repo.identity(fold), spec, state, tuple(fit_ids), tuple(skipped_ids)
    )
