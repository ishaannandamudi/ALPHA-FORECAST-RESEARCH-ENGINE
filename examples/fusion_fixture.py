"""Bounded causal synthetic producer functions on the native AFRE4 dataset."""

from dataclasses import dataclass
from math import sin

from afre.feature_store.models import AvailabilityEvidence
from afre.fusion import (
    ExternalFusionDefinition,
    ExternalFusionOutput,
    FusionEngine,
    FusionFamily,
    FusionKind,
    FusionRepository,
    FusionSourceReference,
    FusionSpec,
    FusionWeights,
)
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.target_engine.definitions import TargetDefinition
from examples.feature_store_demo import SOURCE
from examples.selection_fixture import SelectionFixture, small_fixture


@dataclass(frozen=True)
class FusionFixture:
    upstream: SelectionFixture
    references: tuple[FusionSourceReference, ...]
    definitions: tuple[ExternalFusionDefinition, ...]
    bindings: tuple[tuple[str, tuple[str, ...]], ...]
    train: tuple[str, ...]
    validation: tuple[str, ...]
    test: tuple[str, ...]
    spec: FusionSpec

    def observations(self, sample_id: str) -> tuple[str, ...]:
        return dict(self.bindings)[sample_id]


def build_fixture(repo: FusionRepository, reverse: bool = False) -> FusionFixture:
    upstream = small_fixture(repo, reverse)
    space = upstream.space
    target = repo.get(TargetDefinition, space.target_id)
    partitions = tuple(
        tuple(
            s
            for s in repo.partition_samples(space.fold_id, p)
            if s.target_definition_id == space.target_id
        )
        for p in (Partition.TRAIN, Partition.VALIDATION, Partition.TEST)
    )
    samples = tuple(s for part in partitions for s in part)
    engine = FusionEngine(repo)
    refs: list[FusionSourceReference] = []
    definitions: list[ExternalFusionDefinition] = []
    grid: dict[str, list[str]] = {s.fingerprint: [] for s in samples}
    for j in reversed(range(2)) if reverse else range(2):
        definition = ExternalFusionDefinition(
            f"synthetic-producer-{j}",
            SOURCE.provenance.system,
            "1",
            target,
            FusionKind.POINT,
            "target-value:" + target.fingerprint,
            SOURCE,
            0,
        )
        outputs = []
        for sample in reversed(samples) if reverse else samples:
            assert sample.origin is not None
            at, index = sample.timestamp_ns, int(sample.security.value) - 1
            # Fixed known functions; no target repository read creates these predictions.
            value = 1.0 / (100.0 + at + index) if j == 0 else sin(float(at + index))
            outputs.append(
                ExternalFusionOutput(
                    definition.fingerprint,
                    sample.fingerprint,
                    sample.origin,
                    value,
                    None,
                    AvailabilityEvidence(at, at, at, at),
                    "initial",
                )
            )
        engine.external(definition, tuple(outputs))
        ref = engine.source(min(outputs, key=lambda o: o.sample_id).fingerprint)
        refs.append(ref)
        definitions.append(definition)
        for output in outputs:
            grid[output.sample_id].append(
                engine.observe(ref.fingerprint, output.fingerprint).fingerprint
            )
    refs = sorted(refs, key=lambda r: r.fingerprint)
    spec = FusionSpec(
        "synthetic-fixed",
        tuple(r.fingerprint for r in refs),
        target.fingerprint,
        target.horizon.fingerprint,
        FusionKind.POINT,
        "target-value:" + target.fingerprint,
        FusionFamily.FIXED_WEIGHT_POINT,
        FusionWeights.SIMPLEX,
        tuple((r.fingerprint, 0.5) for r in refs),
        space.dataset_id,
        space.fold_id,
        0,
    )
    return FusionFixture(
        upstream,
        tuple(refs),
        tuple(sorted(definitions, key=lambda d: d.logical_id)),
        tuple(sorted((i, tuple(sorted(v))) for i, v in grid.items())),
        tuple(sorted(s.fingerprint for s in partitions[0])),
        tuple(sorted(s.fingerprint for s in partitions[1])),
        tuple(sorted(s.fingerprint for s in partitions[2])),
        spec,
    )


def apply_partition(
    repo: FusionRepository,
    fixture: FusionFixture,
    artifact_id: str,
    sample_ids: tuple[str, ...],
) -> tuple[str, ...]:
    engine = FusionEngine(repo)
    return tuple(
        sorted(
            engine.apply(
                artifact_id,
                i,
                fixture.observations(i),
                repo.get(ResearchSample, i).timestamp_ns,
            ).fingerprint
            for i in sample_ids
        )
    )
