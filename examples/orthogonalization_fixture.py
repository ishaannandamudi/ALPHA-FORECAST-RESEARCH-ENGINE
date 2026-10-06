"""Independent offline causal fixtures."""

import math
from dataclasses import dataclass

from afre.feature_store.models import AvailabilityEvidence, SourceReference
from afre.hashing import bytes_digest
from afre.lineage import ProvenanceRef
from afre.orthogonalization import (
    AlignedSignalRow,
    GenericSignalSource,
    OrthogonalizationEngine,
    OrthogonalizationMode,
    OrthogonalizationRepository,
    OrthogonalizationSpec,
    OrthogonalQuality,
    OrthogonalSignalValue,
    ProjectionArtifact,
    SignalReference,
    SignalSourceType,
)
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.statistical_models.definitions import BaselineModelSpec
from afre.target_engine.definitions import TargetDefinition
from examples.uncertainty_fixture import (
    UncertaintyFixture,
)
from examples.uncertainty_fixture import (
    build_fixture as uncertainty_fixture,
)


@dataclass(frozen=True)
class OrthogonalFixture:
    upstream: UncertaintyFixture
    spec: OrthogonalizationSpec
    projection: ProjectionArtifact
    rows: tuple[AlignedSignalRow, ...]
    residuals: tuple[OrthogonalSignalValue, ...]

    def partition(self, value: Partition) -> tuple[AlignedSignalRow, ...]:
        return tuple(r for r in self.rows if r.partition is value)

    def residual_ids(self, value: Partition) -> tuple[str, ...]:
        samples = {r.sample_id for r in self.partition(value)}
        return tuple(v.fingerprint for v in self.residuals if v.sample_id in samples)


def generic_reference(name: str) -> SignalReference:
    return SignalReference(
        name,
        SignalSourceType.GENERIC,
        ("neutral.synthetic-v1", name),
        "neutral-offline",
        "1",
        name,
        "1",
        "synthetic-unit",
    )


def generic_source(
    ref: SignalReference,
    sample: ResearchSample,
    value: float | None,
    revision: str = "1",
    late: int = 0,
) -> GenericSignalSource:
    assert sample.origin is not None
    origin = sample.origin
    evidence = ProvenanceRef(
        ref.provider,
        ref.signal_id + ":" + sample.fingerprint + ":" + revision,
        ref.provider_version,
        bytes_digest(str(value).encode()),
    )
    dataset = ProvenanceRef(
        ref.provider, "synthetic-input-dataset", "1", bytes_digest(b"neutral-causal-inputs")
    ).fingerprint
    at = origin.timestamp_ns + late
    return GenericSignalSource(
        ref,
        origin,
        AvailabilityEvidence(at, at, at, at, upstream_publication_ns=origin.timestamp_ns),
        SourceReference(evidence, dataset),
        value,
        OrthogonalQuality.AVAILABLE if value is not None else OrthogonalQuality.MISSING,
        revision,
    )


def build_rows(
    repo: OrthogonalizationRepository,
    fold_id: str,
    target: TargetDefinition,
    cutoff_ns: int,
    *,
    reverse: bool = False,
    mode: OrthogonalizationMode = OrthogonalizationMode.TEMPORAL_PANEL,
    tag: str = "main",
    perfect: bool = False,
) -> tuple[OrthogonalizationSpec, tuple[AlignedSignalRow, ...]]:
    e = OrthogonalizationEngine(repo)
    candidate, xref, zref = tuple(
        generic_reference(tag + "-" + n) for n in ("candidate", "x", "z")
    )
    refs = (xref,) if perfect else (xref, zref)
    for ref in reversed((candidate, *refs)) if reverse else (candidate, *refs):
        e.register(ref)
    spec = OrthogonalizationSpec(
        candidate, tuple(reversed(refs)) if reverse else refs, mode, fold_id, cutoff_ns, target
    )
    samples = tuple(
        s
        for part in (Partition.TRAIN, Partition.VALIDATION, Partition.TEST)
        for s in repo.partition_samples(fold_id, part)
    )
    securities = sorted({s.security.fingerprint for s in samples})
    times = sorted({s.timestamp_ns for s in samples})
    rows = []
    for sample in reversed(samples) if reverse else samples:
        i = securities.index(sample.security.fingerprint) - 1.5
        t = times.index(sample.timestamp_ns) + 1.0
        x = i + 0.4 * t
        z = i * i + math.sin(t)
        u = i * i * i + 0.25 * math.cos(t)
        values = {
            candidate: 1.0 + 2.0 * x if perfect else 1.0 + 2.0 * x - 0.5 * z + 0.3 * u,
            xref: x,
            zref: z,
        }
        observations = []
        for ref in (candidate, *refs):
            source = e.publish_generic(generic_source(ref, sample, values[ref]))
            observations.append(e.bind(ref, source.fingerprint, sample.fingerprint).fingerprint)
        rows.append(
            e.align(spec, tuple(reversed(observations)) if reverse else tuple(observations))
        )
    return spec, tuple(
        sorted(rows, key=lambda r: (r.origin.timestamp_ns, r.origin.instrument.fingerprint))
    )


def build_fixture(
    repo: OrthogonalizationRepository, reverse: bool = False
) -> OrthogonalFixture:
    upstream = uncertainty_fixture(repo, reverse)
    from afre.statistical_models.artifacts import FittedModelArtifact

    native = repo.get(FittedModelArtifact, upstream.covariances[0].model_id)
    baseline = repo.get(BaselineModelSpec, native.spec_id)
    spec, rows = build_rows(repo, baseline.fold_id, baseline.target, 40, reverse=reverse)
    e = OrthogonalizationEngine(repo)
    train = tuple(r.fingerprint for r in rows if r.partition is Partition.TRAIN)
    projection = e.fit(spec, tuple(reversed(train)) if reverse else train, 40)
    residuals = tuple(
        e.residual(projection.fingerprint, r.fingerprint, r.origin.timestamp_ns)
        for r in rows
        if r.partition in (Partition.VALIDATION, Partition.TEST)
    )
    return OrthogonalFixture(upstream, spec, projection, rows, residuals)
