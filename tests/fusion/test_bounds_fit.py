"""Configured limits and explicit QR failures, with no pseudo-inverse or hidden ridge."""

from dataclasses import replace
from math import fsum, sqrt

import pytest

from afre.fusion import (
    ExternalFusionOutput,
    FusionBounds,
    FusionEngine,
    FusionFamily,
    FusionIntercept,
    FusionKind,
    FusionNormalization,
    FusionObservation,
    FusionRepository,
    FusionWeights,
)
from afre.fusion.external import ExternalFusionDefinition
from afre.schema import ContractError
from examples.fusion_fixture import FusionFixture

Case = tuple[FusionRepository, FusionFixture]


@pytest.mark.parametrize(
    "name",
    (
        "sources",
        "train_rows",
        "prediction_rows",
        "probability_components",
        "probability_atoms",
        "diversity_cells",
        "comparisons",
        "artifacts",
        "payload_bytes",
        "snapshot_bytes",
        "publication_rows",
        "lineage_nodes",
        "lineage_depth",
    ),
)
def test_absolute_bounds(name: str) -> None:
    with pytest.raises(ContractError, match="hard bounds"):
        replace(FusionBounds(), **{name: 0})


@pytest.mark.parametrize("near", (False, True))
def test_rank_and_condition_failure(fusion_case: Case, near: bool) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    spec = replace(
        f.spec,
        family=FusionFamily.LEARNED_LINEAR_POINT,
        weights=(),
        weight_policy=FusionWeights.UNCONSTRAINED_QR,
        intercept_policy=FusionIntercept.WITH_INTERCEPT,
        rank_tolerance=1e-16 if near else 1e-12,
        condition_limit=1e4,
    )
    bindings = []
    for index, sample in enumerate(f.train):
        obs = tuple(repo.get(FusionObservation, i) for i in f.observations(sample))
        raw = repo.get(ExternalFusionOutput, obs[1].output_id)
        x = obs[0].value
        assert x is not None
        changed = replace(
            raw, value=x + (1e-9 * index**2 if near else 0.0), revision="collinear"
        )
        e.external(repo.get(ExternalFusionDefinition, raw.definition_id), (changed,))
        replacement = e.observe(obs[1].source_id, changed.fingerprint)
        bindings.append((sample, (obs[0].fingerprint, replacement.fingerprint)))
    with pytest.raises(ContractError, match="ill-conditioned" if near else "rank-deficient"):
        e.fit(spec, 40, 40, 40, tuple(bindings))


def test_signal_train_standardization(fusion_case: Case) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    refs = []
    grid: dict[str, list[str]] = {s: [] for s, _ in f.bindings}
    for old in f.definitions:
        definition = replace(old, kind=FusionKind.SCALAR_SIGNAL, unit="synthetic-unit")
        outputs = []
        for sample_id in grid:
            old_obs = next(
                repo.get(FusionObservation, i)
                for i in f.observations(sample_id)
                if repo.get(FusionObservation, i).source_id
                == next(r.fingerprint for r in f.references if r.source_id == old.logical_id)
            )
            outputs.append(
                replace(
                    repo.get(ExternalFusionOutput, old_obs.output_id),
                    definition_id=definition.fingerprint,
                )
            )
        e.external(definition, tuple(outputs))
        ref = e.source(min(outputs, key=lambda o: o.sample_id).fingerprint)
        refs.append(ref)
        for output in outputs:
            grid[output.sample_id].append(
                e.observe(ref.fingerprint, output.fingerprint).fingerprint
            )
    spec = replace(
        f.spec,
        name="standardized-signals",
        source_ids=tuple(r.fingerprint for r in refs),
        weights=tuple((r.fingerprint, 0.5) for r in refs),
        kind=FusionKind.SCALAR_SIGNAL,
        family=FusionFamily.FIXED_SIGNAL_BLEND,
        unit="synthetic-unit",
        output_unit="dimensionless",
        normalization=FusionNormalization.TRAIN_STANDARDIZE,
    )
    a = e.fit(spec, 40, 40, 40, tuple((s, tuple(grid[s])) for s in f.train))
    for j, _i in enumerate(spec.source_ids):
        values = tuple(r.values[j] for r in a.rows)
        center = fsum(values) / len(values)
        scale = sqrt(fsum((x - center) ** 2 for x in values) / len(values))
        assert a.centers[j] == center and a.scales[j] == scale
        assert all(r.response is None and r.target_id is None for r in a.rows)
    result = e.apply(a.fingerprint, f.validation[0], tuple(grid[f.validation[0]]), 40)
    assert result.unit == "dimensionless" and result.value is not None

    forecasts = tuple(
        e.apply(a.fingerprint, sample, tuple(grid[sample]), 40).fingerprint
        for sample in f.validation
    )
    with pytest.raises(ContractError, match="target-unit forecast"):
        e.trial_pool(((spec.fingerprint, forecasts),))


@pytest.mark.parametrize(
    "name",
    (
        "sources",
        "train_rows",
        "diversity_cells",
        "payload_bytes",
        "snapshot_bytes",
        "lineage_nodes",
        "lineage_depth",
    ),
)
def test_configured_bounds_fail_before_work(fusion_case: Case, name: str) -> None:
    repo, f = fusion_case
    e = FusionEngine(repo)
    a = e.fit(f.spec, 0, 0, 0)
    repo.fusion_bounds = replace(repo.fusion_bounds, **{name: 1})
    with pytest.raises(ContractError, match="bound"):
        if name == "train_rows":
            spec = replace(
                f.spec,
                weights=(),
                family=FusionFamily.LEARNED_LINEAR_POINT,
                weight_policy=FusionWeights.UNCONSTRAINED_QR,
            )
            e.fit(spec, 40, 40, 40, tuple((i, f.observations(i)) for i in f.train))
        elif name in ("lineage_nodes", "lineage_depth"):
            output = e.apply(
                a.fingerprint, f.validation[0], f.observations(f.validation[0]), 40
            )
            e.audit(output.fingerprint)
        elif name == "diversity_cells":
            e.diversity(
                f.spec.source_ids,
                tuple(i for s in f.validation for i in f.observations(s)),
                100,
            )
        else:
            e.apply(a.fingerprint, f.validation[0], f.observations(f.validation[0]), 40)
