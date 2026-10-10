"""Actual native AFRE5/6/7/10/11/12/13/14 and AFRE16 fusion sources."""

from dataclasses import dataclass

from afre.fusion import (
    FusionEngine,
    FusionFamily,
    FusionKind,
    FusionRepository,
    FusionSpec,
    FusionWeights,
)
from afre.fusion.metadata import FusionMetadata
from afre.orthogonalization import OrthogonalizationEngine
from afre.regime_conditioned.artifacts import RegimeConditionedSample
from afre.research_datasets.schema import Partition
from afre.research_datasets.splits import FoldDefinition
from afre.schema import require
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition
from afre.uncertainty.sources import source_for
from examples.orthogonalization_fixture import build_rows
from examples.regime_horizon_fixture import real_horizons
from examples.uncertainty_fixture import build_fixture as uncertainty_fixture


@dataclass(frozen=True)
class NativeFusionResult:
    outputs: tuple[tuple[str, str], ...]
    metadata_id: str
    probability_id: str


def fuse_sources(
    repo: FusionRepository,
    name: str,
    output_ids: tuple[str, ...],
    kind: FusionKind = FusionKind.POINT,
) -> str:
    engine = FusionEngine(repo)
    projected = tuple(source_for(repo, i) for i in output_ids)
    first = projected[0]
    require(
        all(s.sample_id == first.sample_id and s.fold_id == first.fold_id for s in projected),
        "exact native fixture sources",
    )
    refs = tuple(engine.source(i, kind) for i in output_ids)
    fold = repo.get(FoldDefinition, first.fold_id)
    declared = fold.training_cutoff_ns
    spec = FusionSpec(
        name,
        tuple(r.fingerprint for r in refs),
        first.target.fingerprint,
        first.target.horizon.fingerprint,
        kind,
        "target-value:" + first.target.fingerprint,
        FusionFamily.FIXED_PROBABILITY_MIXTURE
        if kind is FusionKind.PROBABILISTIC
        else FusionFamily.FIXED_WEIGHT_POINT,
        FusionWeights.SIMPLEX,
        tuple((r.fingerprint, 1.0 / len(refs)) for r in refs),
        fold.dataset_id,
        fold.fingerprint,
        declared,
    )
    ready = max(declared, *(r.available_ns for r in refs))
    artifact = engine.fit(spec, declared, ready, ready)
    observations = tuple(
        engine.observe(r.fingerprint, i).fingerprint
        for r, i in zip(refs, output_ids, strict=True)
    )
    return engine.apply(
        artifact.fingerprint, first.sample_id, observations, first.origin.timestamp_ns
    ).fingerprint


def native_fixture(repo: FusionRepository) -> NativeFusionResult:
    upstream = uncertainty_fixture(repo)
    engine = FusionEngine(repo)
    outputs = []
    for name in (
        "point",
        "gaussian",
        "calibrated",
        "event",
        "hard-regime",
        "mixture",
        "nonlinear",
        "sequence",
    ):
        identity = upstream.ids(name)[0]
        outputs.append((name, fuse_sources(repo, "native-" + name, (identity,))))
    mixture = upstream.ids("mixture")[0]
    source = source_for(repo, mixture)
    gaussian = next(
        i for i in upstream.ids("gaussian") if source_for(repo, i).sample_id == source.sample_id
    )
    probability = fuse_sources(
        repo, "native-nested-mixture", (mixture, gaussian), FusionKind.PROBABILISTIC
    )
    spec, rows = build_rows(repo, source.fold_id, source.target, 40, tag="fusion-residual")
    orthogonal = OrthogonalizationEngine(repo)
    projection = orthogonal.fit(
        spec, tuple(r.fingerprint for r in rows if r.partition is Partition.TRAIN), 40
    )
    row = next(r for r in rows if r.partition is Partition.VALIDATION)
    residual = orthogonal.residual(
        projection.fingerprint, row.fingerprint, row.origin.timestamp_ns
    )
    ref = engine.source(residual.fingerprint)
    fold = repo.get(FoldDefinition, spec.fold_id)
    blend_spec = FusionSpec(
        "native-residual",
        (ref.fingerprint,),
        source.target.fingerprint,
        source.target.horizon.fingerprint,
        FusionKind.SCALAR_SIGNAL,
        residual.unit,
        FusionFamily.FIXED_SIGNAL_BLEND,
        FusionWeights.SIMPLEX,
        ((ref.fingerprint, 1.0),),
        fold.dataset_id,
        fold.fingerprint,
        40,
    )
    artifact = engine.fit(blend_spec, 40, 40, 40)
    observation = engine.observe(ref.fingerprint, residual.fingerprint)
    output = engine.apply(
        artifact.fingerprint, row.sample_id, (observation.fingerprint,), row.origin.timestamp_ns
    )
    outputs.append(("orthogonal", output.fingerprint))
    from afre.fusion import FusedForecast

    point_output = repo.get(FusedForecast, dict(outputs)["point"])
    uncertainty = next(
        i
        for i in upstream.results("point")
        if repo.get(ForecastUncertaintyDecomposition, i).sample_id == point_output.sample_id
    )
    metadata = FusionMetadata(point_output.fingerprint, (uncertainty,), 60)
    engine._publish((metadata,))
    return NativeFusionResult(tuple(outputs), metadata.fingerprint, probability)


def horizon_fixture(repo: FusionRepository) -> tuple[tuple[int, str], ...]:
    results = []
    for _, forecasts in real_horizons(repo):
        forecast = forecasts[0]
        source = source_for(repo, forecast.fingerprint)
        sample = repo.get(RegimeConditionedSample, forecast.observation_id)
        require(sample.sample_id == source.sample_id, "actual horizon sample")
        assert source.target.horizon.duration_ns is not None
        output = fuse_sources(
            repo,
            "actual-" + str(source.target.horizon.duration_ns),
            (forecast.fingerprint, forecast.base_forecast_id),
        )
        results.append((source.target.horizon.duration_ns, output))
    return tuple(results)
