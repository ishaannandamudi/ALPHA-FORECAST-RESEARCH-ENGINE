"""Deterministic TRAIN rows and pivoted Householder QR with exact replay."""

from math import fsum, sqrt
from typing import TYPE_CHECKING

from afre.fusion.artifacts import FusionArtifact, FusionTrainingRow
from afre.fusion.compatibility import observations
from afre.fusion.definitions import FusionSourceReference, FusionSpec
from afre.fusion.fixed import fixed_weights
from afre.fusion.guards import train_only
from afre.fusion.schema import FusionFamily, FusionIntercept, FusionNormalization
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import FoldDefinition
from afre.schema import require
from afre.statistical_models.linear_algebra import finite, householder_qr
from afre.target_engine.models import TargetVintage
from afre.target_engine.validation import target_known_by_cutoff

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository


def training_rows(
    repo: "FusionRepository",
    spec: FusionSpec,
    bindings: tuple[tuple[str, tuple[str, ...]], ...],
    cutoff_ns: int,
) -> tuple[FusionTrainingRow, ...]:
    samples = tuple(
        s
        for s in repo.partition_samples(spec.fold_id, Partition.TRAIN)
        if s.target_definition_id == spec.target_id
    )
    sealed = {
        r[0]
        for r in repo._connection.execute(
            "SELECT sample_id FROM r_memberships WHERE partition=?", (Partition.TEST.value,)
        )
    }
    require(
        bool(samples)
        and len(samples) <= min(spec.bounds.train_rows, repo.fusion_bounds.train_rows)
        and {s.fingerprint for s in samples} == {i for i, _ in bindings}
        and len(bindings) == len(samples)
        and not sealed.intersection(i for i, _ in bindings),
        "exact complete admitted TRAIN grid bound; sealed TEST excluded",
    )
    by_sample = dict(bindings)
    rows = []
    learned = spec.family is FusionFamily.LEARNED_LINEAR_POINT
    ids = tuple(s.target_id for s in samples if s.target_id is not None)
    with train_only(repo, ids):
        for sample in sorted(samples, key=lambda s: s.fingerprint):
            with repo.feature_only():
                obs = observations(
                    repo, spec, sample.fingerprint, by_sample[sample.fingerprint]
                )
            require(
                tuple(o.source_id for o in obs) == spec.source_ids
                and all(o.value is not None for o in obs),
                "complete TRAIN source columns required",
            )
            require(
                sample.origin is not None and sample.origin.timestamp_ns < cutoff_ns,
                "TRAIN origin before fit cutoff",
            )
            target = None
            if learned:
                require(sample.target_id is not None, "TRAIN truth witness required")
                assert sample.target_id is not None
                target = repo.resolve(TargetVintage, sample.target_id)
                require(
                    target_known_by_cutoff(target, cutoff_ns)
                    and target.origin == sample.origin
                    and target.definition.fingerprint == spec.target_id
                    and type(target.value) is float,
                    "TRAIN response causal exact target",
                )
            available = max(
                *(o.available_ns for o in obs),
                target.clocks.final_available_ns if target else 0,
            )
            require(available <= cutoff_ns, "TRAIN evidence after declared cutoff")
            rows.append(
                FusionTrainingRow(
                    sample.fingerprint,
                    tuple(o.fingerprint for o in obs),
                    target.fingerprint if target else None,
                    target.value if target else None,
                    tuple(o.value for o in obs if o.value is not None),
                    available,
                )
            )
    return tuple(rows)


def fitted_values(
    spec: FusionSpec,
    rows: tuple[FusionTrainingRow, ...],
    cutoff_ns: int,
    computed_ns: int,
    available_ns: int,
) -> FusionArtifact:
    width = len(spec.source_ids)
    centers, scales = (0.0,) * width, (1.0,) * width
    weights, intercept, rank, condition = fixed_weights(spec), spec.fixed_intercept, 0, None
    assumption = "fixed-declared-weights-v1"
    if spec.normalization is FusionNormalization.TRAIN_STANDARDIZE:
        require(bool(rows), "standardization requires TRAIN evidence")
        centers = tuple(
            finite(fsum(r.values[j] for r in rows) / len(rows)) for j in range(width)
        )
        scales = tuple(
            finite(sqrt(fsum((r.values[j] - centers[j]) ** 2 for r in rows) / len(rows)))
            for j in range(width)
        )
        require(all(s > 0 for s in scales), "TRAIN standardization zero scale")
        assumption = "fixed-weight-TRAIN-population-standardization-v1"
    elif spec.family is FusionFamily.LEARNED_LINEAR_POINT:
        require(
            bool(rows) and all(r.response is not None for r in rows), "learned TRAIN responses"
        )
        with_intercept = spec.intercept_policy is FusionIntercept.WITH_INTERCEPT
        solution = householder_qr(
            tuple(((1.0,) if with_intercept else ()) + r.values for r in rows),
            tuple(r.response for r in rows if r.response is not None),
            spec.rank_tolerance,
            spec.condition_limit,
        )
        coefficients = solution.coefficients[1:] if with_intercept else solution.coefficients
        weights = tuple(zip(spec.source_ids, coefficients, strict=True))
        intercept = solution.coefficients[0] if with_intercept else 0.0
        rank, condition = solution.rank, solution.condition_proxy
        assumption = "unconstrained-QR-on-causal-out-of-sample-TRAIN-predictions-v1"
    else:
        require(not rows, "untransformed fixed fusion cannot contain hidden fitting evidence")
    return FusionArtifact(
        spec.fingerprint,
        spec.source_ids,
        weights,
        intercept,
        centers,
        scales,
        rows,
        rank,
        condition,
        cutoff_ns,
        computed_ns,
        available_ns,
        assumption,
    )


def frozen_inputs(repo: "FusionRepository", spec: FusionSpec, artifact: FusionArtifact) -> None:
    """Check persisted source witnesses and fit clocks without reading a response."""
    learned = (
        spec.family is FusionFamily.LEARNED_LINEAR_POINT
        or spec.normalization is FusionNormalization.TRAIN_STANDARDIZE
    )
    fold = repo.get(FoldDefinition, spec.fold_id)
    require(
        artifact.fit_cutoff_ns == (fold.training_cutoff_ns if learned else spec.declared_ns)
        and artifact.available_ns
        >= max(repo.get(FusionSourceReference, i).available_ns for i in spec.source_ids),
        "frozen fusion exact cutoff/source availability",
    )
    if not learned:
        return
    samples = {
        s.fingerprint: s
        for s in repo.partition_samples(spec.fold_id, Partition.TRAIN)
        if s.target_definition_id == spec.target_id
    }
    require(
        len(samples) == len(artifact.rows)
        and set(samples) == {r.sample_id for r in artifact.rows},
        "frozen fusion exact complete TRAIN grid",
    )
    for row in artifact.rows:
        sample = samples[row.sample_id]
        obs = observations(repo, spec, row.sample_id, row.observation_ids)
        require(
            tuple(o.source_id for o in obs) == spec.source_ids
            and row.values == tuple(o.value for o in obs)
            and sample.timestamp_ns < artifact.fit_cutoff_ns
            and row.data_available_ns >= max(o.available_ns for o in obs)
            and row.target_id
            == (sample.target_id if spec.family is FusionFamily.LEARNED_LINEAR_POINT else None),
            "frozen fusion exact source/TRAIN witness",
        )


def fit_for(
    repo: "FusionRepository",
    spec: FusionSpec,
    bindings: tuple[tuple[str, tuple[str, ...]], ...],
    cutoff_ns: int,
    computed_ns: int,
    available_ns: int,
) -> FusionArtifact:
    learned = (
        spec.family is FusionFamily.LEARNED_LINEAR_POINT
        or spec.normalization is FusionNormalization.TRAIN_STANDARDIZE
    )
    fold = repo.get(FoldDefinition, spec.fold_id)
    require(
        cutoff_ns == (fold.training_cutoff_ns if learned else spec.declared_ns)
        and cutoff_ns <= computed_ns <= available_ns,
        "fusion exact fit cutoff/clocks",
    )
    rows = training_rows(repo, spec, bindings, cutoff_ns) if learned else ()
    require(learned or not bindings, "fixed fusion has no fitting bindings")
    refs = tuple(repo.get(FusionSourceReference, i) for i in spec.source_ids)
    require(
        available_ns >= max(r.available_ns for r in refs),
        "fusion before source artifact availability",
    )
    return fitted_values(spec, rows, cutoff_ns, computed_ns, available_ns)
