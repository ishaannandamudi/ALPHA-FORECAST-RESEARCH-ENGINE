"""Stable exact laws: empirical atoms are actual values, never residual aliases."""

from dataclasses import dataclass
from math import erfc, fsum, sqrt

from afre.ids import validate_fingerprint
from afre.schema import Artifact, contract, require


@contract("svc_law_component")
@dataclass(frozen=True, slots=True)
class ServiceLawComponent(Artifact):
    identity: str
    weight: float
    family: str
    location: float
    scale: float
    atoms: tuple[float, ...] = ()
    quantiles: tuple[tuple[float, float], ...] = ()

    def _normalize(self) -> None:
        object.__setattr__(self, "atoms", tuple(sorted(self.atoms)))
        object.__setattr__(self, "quantiles", tuple(sorted(self.quantiles)))

    def _validate(self) -> None:
        require(
            self.weight > 0 and self.family in ("GAUSSIAN", "EMPIRICAL", "QUANTILES"),
            "invalid public law component",
        )
        require(
            len(self.atoms) <= 10000 and len(self.quantiles) <= 1024,
            "public law atom/quantile bound",
        )
        require(
            (
                self.family == "GAUSSIAN"
                and self.scale > 0
                and not self.atoms
                and not self.quantiles
            )
            or (
                self.family == "EMPIRICAL"
                and self.scale == 0
                and bool(self.atoms)
                and not self.quantiles
            )
            or (
                self.family == "QUANTILES"
                and self.scale == 0
                and not self.atoms
                and bool(self.quantiles)
            ),
            "public law family semantics",
        )
        require(
            all(0 < q < 1 for q, _ in self.quantiles)
            and len({q for q, _ in self.quantiles}) == len(self.quantiles)
            and all(
                a[1] <= b[1] for a, b in zip(self.quantiles, self.quantiles[1:], strict=False)
            ),
            "public quantile order",
        )


@contract("svc_probability")
@dataclass(frozen=True, slots=True)
class ServiceProbabilityLaw(Artifact):
    kind: str
    native_law_id: str
    components: tuple[ServiceLawComponent, ...]

    def _normalize(self) -> None:
        self.ordered("components", "identity")

    def _validate(self) -> None:
        require(
            0 < len(self.components) <= 32
            and abs(fsum(c.weight for c in self.components) - 1.0) <= 1e-12,
            "public mixture simplex/component bound",
        )
        require(
            self.kind in ("GAUSSIAN", "EMPIRICAL", "MIXTURE", "QUANTILES"),
            "unsupported public law",
        )
        require(
            (self.kind == "MIXTURE" and all(c.family != "QUANTILES" for c in self.components))
            or (len(self.components) == 1 and self.components[0].family == self.kind),
            "public probability semantics",
        )

    def threshold_probability(self, threshold: float, comparison: str) -> float:
        Artifact._validate_scalar(threshold)
        require(
            type(threshold) is float and comparison in ("GT", "GE", "LT", "LE"),
            "invalid threshold request",
        )
        require(self.kind != "QUANTILES", "UNAVAILABLE: quantile-only CDF")
        values = []
        for c in self.components:
            if c.family == "GAUSSIAN":
                z = (threshold - c.location) / c.scale / sqrt(2)
                p = 0.5 * erfc(z if comparison in ("GT", "GE") else -z)
            else:
                p = sum(
                    a > threshold
                    if comparison == "GT"
                    else a >= threshold
                    if comparison == "GE"
                    else a < threshold
                    if comparison == "LT"
                    else a <= threshold
                    for a in c.atoms
                ) / len(c.atoms)
            values.append(c.weight * p)
        return min(1.0, max(0.0, fsum(values)))


@contract("svc_calibration")
@dataclass(frozen=True, slots=True)
class ServiceCalibration(Artifact):
    state: str
    method: str
    artifact_id: str | None
    version: str
    fit_cutoff_ns: int | None
    available_ns: int | None
    full_distribution_preserved: bool

    def _validate(self) -> None:
        require(
            self.state in ("UNCALIBRATED", "CALIBRATED") and self.version == "1.0",
            "calibration state/version",
        )
        calibrated = self.state == "CALIBRATED"
        require(
            calibrated == (self.artifact_id is not None)
            and calibrated == (self.fit_cutoff_ns is not None)
            and calibrated == (self.available_ns is not None)
            and (
                calibrated or (self.method == "NONE" and not self.full_distribution_preserved)
            ),
            "calibration exact metadata",
        )
        if self.artifact_id is not None:
            validate_fingerprint(self.artifact_id, "c_state")


@contract("svc_output")
@dataclass(frozen=True, slots=True)
class ForecastOutput(Artifact):
    artifact_id: str
    producer_id: str
    target_id: str
    horizon_id: str
    unit: str
    point: float | None
    probability: ServiceProbabilityLaw | None
    quantiles: tuple[tuple[float, float], ...]
    thresholds: tuple[tuple[str, float, float], ...]
    interval: tuple[float, float] | None
    calibration: ServiceCalibration
    available_ns: int

    def _normalize(self) -> None:
        object.__setattr__(self, "quantiles", tuple(sorted(self.quantiles)))
        object.__setattr__(self, "thresholds", tuple(sorted(self.thresholds)))

    def _validate(self) -> None:
        for identity in (self.artifact_id, self.producer_id, self.target_id, self.horizon_id):
            validate_fingerprint(identity)
        require(
            len(self.quantiles) <= 256
            and len(self.thresholds) <= 256
            and len({q for q, _ in self.quantiles}) == len(self.quantiles)
            and all(0 < q < 1 for q, _ in self.quantiles)
            and all(
                a[1] <= b[1] for a, b in zip(self.quantiles, self.quantiles[1:], strict=False)
            ),
            "output quantile/threshold bound/order",
        )
        require(
            self.point is not None or self.probability is not None or bool(self.quantiles),
            "INSUFFICIENT_DATA: forecast has no supported output",
        )
        require(
            all(c in ("GT", "GE", "LT", "LE") and 0 <= p <= 1 for c, _, p in self.thresholds),
            "threshold semantics",
        )
        require(
            self.interval is None or self.interval[0] <= self.interval[1], "interval ordering"
        )
