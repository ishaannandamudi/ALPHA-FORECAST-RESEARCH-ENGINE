"""Frozen aligned rows, TRAIN coefficients and versioned causal residual features."""

from dataclasses import dataclass

from afre.forecast import ForecastOrigin
from afre.ids import validate_fingerprint
from afre.orthogonalization.schema import OrthogonalQuality
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, contract, require
from afre.statistical_models.artifacts import PointMetric, unique_ids


@contract("ort_row")
@dataclass(frozen=True, slots=True)
class AlignedSignalRow(Artifact):
    spec_id: str
    sample_id: str
    origin: ForecastOrigin
    partition: Partition
    observation_ids: tuple[str, ...]
    candidate: float | None
    references: tuple[float | None, ...]
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "ort_spec")
        validate_fingerprint(self.sample_id, "r_sample")
        unique_ids(self.observation_ids, "ort_observation")
        require(
            len(self.observation_ids) == len(self.references) + 1
            and 0 < len(self.references) <= 16,
            "aligned row dimensions",
        )
        require(
            self.available_ns <= self.origin.availability_cutoff_ns, "aligned row unavailable"
        )


@contract("ort_matrix")
@dataclass(frozen=True, slots=True)
class RedundancyMatrix(Artifact):
    spec_id: str
    row_ids: tuple[str, ...]
    intersection_sample_ids: tuple[str, ...]
    excluded_sample_ids: tuple[str, ...]
    partition: Partition
    pearson: tuple[tuple[PointMetric, ...], ...]
    spearman: tuple[tuple[PointMetric, ...], ...]
    available_ns: int

    def _normalize(self) -> None:
        for n in ("row_ids", "intersection_sample_ids", "excluded_sample_ids"):
            unique_ids(getattr(self, n))
            object.__setattr__(self, n, tuple(sorted(getattr(self, n))))

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "ort_spec")
        require(
            bool(self.row_ids)
            and len(self.pearson) == len(self.spearman) <= 17
            and all(len(r) == len(self.pearson) for r in (*self.pearson, *self.spearman)),
            "redundancy matrix shape",
        )

    @property
    def absolute_pearson(self) -> tuple[tuple[float | None, ...], ...]:
        return tuple(
            tuple(abs(m.value) if m.value is not None else None for m in row)
            for row in self.pearson
        )


@contract("ort_projection")
@dataclass(frozen=True, slots=True)
class ProjectionArtifact(Artifact):
    spec_id: str
    row_ids: tuple[str, ...]
    train_sample_ids: tuple[str, ...]
    candidate_values: tuple[float, ...]
    reference_ids: tuple[str, ...]
    centers: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    design_rank: int
    condition: float
    train_metrics: tuple[PointMetric, ...]
    train_residual_variance: float
    vif: tuple[float | None, ...]
    matrix_id: str
    cutoff_ns: int
    computed_ns: int
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.spec_id, "ort_spec")
        validate_fingerprint(self.matrix_id, "ort_matrix")
        unique_ids(self.row_ids, "ort_row")
        unique_ids(self.train_sample_ids, "r_sample")
        unique_ids(self.reference_ids, "ort_reference")
        d = len(self.coefficients)
        require(
            0 < d <= 16
            and len(self.reference_ids)
            == len(self.centers)
            == len(self.scales)
            == len(self.vif)
            == d
            and all(s > 0 for s in self.scales),
            "projection dimensions/scales",
        )
        require(
            len(self.row_ids) == len(self.train_sample_ids) == len(self.candidate_values)
            and self.condition >= 1
            and self.train_residual_variance >= 0,
            "projection TRAIN statistics",
        )
        require(
            self.cutoff_ns <= self.computed_ns <= self.available_ns,
            "projection actual fit clocks",
        )


@contract("ort_value")
@dataclass(frozen=True, slots=True)
class OrthogonalSignalValue(Artifact):
    projection_id: str
    row_id: str
    sample_id: str
    origin: ForecastOrigin
    raw_candidate: float | None
    projected: float | None
    residual: float | None
    unit: str
    quality: OrthogonalQuality
    computed_ns: int
    available_ns: int

    def _validate(self) -> None:
        validate_fingerprint(self.projection_id, "ort_projection")
        validate_fingerprint(self.row_id, "ort_row")
        validate_fingerprint(self.sample_id, "r_sample")
        present = self.quality is OrthogonalQuality.AVAILABLE
        require(
            all(
                (v is not None) == present
                for v in (self.raw_candidate, self.projected, self.residual)
            ),
            "residual quality/payload",
        )
        require(
            self.origin.timestamp_ns
            <= self.computed_ns
            <= self.available_ns
            <= self.origin.availability_cutoff_ns,
            "residual actual computation/historical availability",
        )
        if present:
            assert self.raw_candidate is not None and self.projected is not None
            require(
                self.residual == self.raw_candidate - self.projected, "residual subtraction"
            )


@contract("ort_audit")
@dataclass(frozen=True, slots=True)
class OrthogonalizationAudit(Artifact):
    root_id: str
    node_ids: tuple[str, ...]
    assertions: tuple[str, ...]

    def _normalize(self) -> None:
        unique_ids(self.node_ids)
        object.__setattr__(self, "node_ids", tuple(sorted(self.node_ids)))

    def _validate(self) -> None:
        require(
            self.root_id in self.node_ids and bool(self.assertions), "orthogonal audit root"
        )
