"""Historically admissible exact TRAIN forecasts; fitted residuals cannot substitute."""

from typing import TYPE_CHECKING

from afre.mixture.artifacts import GateModelArtifact, GateTrainingRow
from afre.mixture.availability import gating_value_for
from afre.mixture.definitions import LearnedGateSpec
from afre.mixture.experts import ExpertForecastBinding, GatingFeatureReference
from afre.mixture.learned import solve_simplex
from afre.research_datasets.schema import Partition
from afre.schema import require
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.mixture.repository import MixtureRepository


def row_for(
    repo: "MixtureRepository",
    spec: LearnedGateSpec,
    sample_id: str,
    binding_ids: tuple[str, ...],
    feature_ids: tuple[str, ...],
) -> GateTrainingRow:
    fold = repo.resolve_fold(spec.fold_id)
    require(fold.training_cutoff_ns == spec.cutoff_ns, "gate exact fold cutoff")
    admitted = {s.fingerprint: s for s in repo.partition_samples(spec.fold_id, Partition.TRAIN)}
    require(sample_id in admitted, "gate accepts admitted TRAIN only")
    sample = admitted[sample_id]
    require(
        sample.origin is not None
        and sample.target_id is not None
        and not sample.dropped
        and sample.target_definition_id == spec.expert_set.target.fingerprint,
        "gate TRAIN sample target/origin",
    )
    assert sample.origin is not None and sample.target_id is not None
    target = repo.resolve(TargetVintage, sample.target_id)
    require(
        target_known_by_cutoff(target, spec.cutoff_ns)
        and target.origin == sample.origin
        and target.definition == spec.expert_set.target,
        "gate TRAIN target unavailable/mismatched",
    )
    bindings = tuple(
        sorted(
            (repo.resolve(ExpertForecastBinding, i) for i in binding_ids),
            key=lambda b: b.expert_id,
        )
    )
    require(
        tuple(b.expert_id for b in bindings) == spec.expert_set.expert_ids,
        "gate requires complete exact TRAIN expert grid",
    )
    from afre.mixture.missingness import binding_reason

    require(
        all(binding_reason(repo, spec.expert_set, b, sample) == "available" for b in bindings),
        "gate TRAIN expert unavailable or noncausal",
    )
    features = tuple(repo.resolve(GatingFeatureReference, i) for i in sorted(feature_ids))
    require(
        tuple(sorted(f.feature_id for f in features)) == spec.gating_feature_ids,
        "gate exact feature definitions",
    )
    for f in features:
        require(f.origin == sample.origin, "gate TRAIN feature origin mismatch")
        gating_value_for(repo, f, spec.expert_set.approved_delivery_attestors)
    assert target.value is not None
    return GateTrainingRow(
        sample_id,
        tuple(b.fingerprint for b in bindings),
        tuple(sorted(feature_ids)),
        target.fingerprint,
        target.value,
        sample.origin,
        target.clocks.final_available_ns,
        spec.fingerprint,
    )


def fit_for(
    repo: "MixtureRepository",
    spec: LearnedGateSpec,
    rows: tuple[GateTrainingRow, ...],
    started_ns: int,
    completed_ns: int,
    available_ns: int,
) -> GateModelArtifact:
    require(
        spec.minimum_samples <= len(rows) <= repo.mixture_bounds.training_samples
        and len({r.sample_id for r in rows}) == len(rows),
        "gate TRAIN sample count/duplicates",
    )
    rows = tuple(sorted(rows, key=lambda r: r.sample_id))
    for r in rows:
        require(
            r == row_for(repo, spec, r.sample_id, r.binding_ids, r.feature_ids),
            "gate row contamination",
        )
    matrix = tuple(
        tuple(repo.resolve(ExpertForecastBinding, i).point for i in r.binding_ids) for r in rows
    )
    require(all(v is not None for row in matrix for v in row), "gate point mean required")
    numeric = tuple(tuple(v for v in row if v is not None) for row in matrix)
    weights, iterations, residual, objective = solve_simplex(
        numeric,
        tuple(r.response for r in rows),
        spec.ridge_penalty,
        spec.maximum_iterations,
        spec.convergence_tolerance,
        repo.mixture_bounds.work_cells,
    )
    return GateModelArtifact(
        spec.fingerprint,
        spec.expert_set.fingerprint,
        tuple(zip(spec.expert_set.expert_ids, weights, strict=True)),
        rows,
        iterations,
        residual,
        objective,
        spec.cutoff_ns,
        started_ns,
        completed_ns,
        available_ns,
    )
