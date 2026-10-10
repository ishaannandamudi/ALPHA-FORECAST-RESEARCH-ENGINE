"""Exact declared target, horizon, unit, fold and source grids."""

from typing import TYPE_CHECKING

from afre.fusion.artifacts import FusionObservation
from afre.fusion.definitions import FusionSourceReference, FusionSpec
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.splits import FoldDefinition
from afre.schema import require
from afre.target_engine.definitions import TargetDefinition

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository


def admit_spec(repo: "FusionRepository", spec: FusionSpec) -> None:
    fold = repo.get(FoldDefinition, spec.fold_id)
    target = repo.get(TargetDefinition, spec.target_id)
    require(
        fold.dataset_id == spec.dataset_id
        and target.horizon.fingerprint == spec.horizon_id
        and spec.declared_ns <= fold.training_cutoff_ns,
        "fusion predeclared exact fold/target",
    )
    refs = tuple(repo.resolve(FusionSourceReference, i) for i in spec.source_ids)
    require(len(refs) <= repo.fusion_bounds.sources, "configured fusion sources bound")
    if spec.fallback_source_id:
        refs += (repo.resolve(FusionSourceReference, spec.fallback_source_id),)
    require(
        all(
            (r.target_id, r.horizon_id, r.kind, r.unit)
            == (spec.target_id, spec.horizon_id, spec.kind, spec.unit)
            for r in refs
        ),
        "INCOMPATIBLE: exact fusion target/horizon/kind/unit",
    )
    keys = tuple((r.family, r.source_id) for r in refs)
    require(
        spec.allow_distinct_versions or len(set(keys)) == len(keys),
        "duplicate logical fusion sources require explicit distinct versions",
    )
    require(
        len({(r.family, r.source_id, r.artifact_id) for r in refs}) == len(refs),
        "duplicate fusion producer/version",
    )
    if spec.source_selection_result_id:
        from afre.selection.results import SelectionResult

        result = repo.get(SelectionResult, spec.source_selection_result_id)
        require(
            result.selected_model_id is not None
            and result.selected_model_id in {r.model_id for r in refs},
            "source-selection context must name an actual selected contributor",
        )
        require(
            result.available_ns <= spec.declared_ns,
            "upstream selection context must precede fusion declaration",
        )
        # This context records upstream source selection, never selects fusion weights.
        for identity in result.validation_ids:
            repo.get_any(identity)


def observations(
    repo: "FusionRepository", spec: FusionSpec, sample_id: str, ids: tuple[str, ...]
) -> tuple[FusionObservation, ...]:
    require(
        len(ids) <= len(spec.source_ids) and len(set(ids)) == len(ids),
        "fusion observation count/duplicates",
    )
    sample = repo.get(ResearchSample, sample_id)
    require(
        not sample.dropped
        and sample.origin is not None
        and sample.target_definition_id == spec.target_id,
        "admitted fusion sample/target",
    )
    values = tuple(repo.resolve(FusionObservation, i) for i in ids)
    require(
        len({o.source_id for o in values}) == len(values)
        and all(
            o.source_id in spec.source_ids
            and o.sample_id == sample_id
            and o.origin == sample.origin
            for o in values
        ),
        "exact fusion source/sample/origin grid",
    )
    return tuple(sorted(values, key=lambda o: o.source_id))
