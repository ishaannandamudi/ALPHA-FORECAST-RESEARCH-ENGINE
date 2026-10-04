"""Fixed event-specific bin maps and monotone isotonic probability maps."""

from afre.calibration.artifacts import (
    CalibrationObservationSet,
    ProbabilityBin,
    ProbabilityMapping,
)
from afre.calibration.definitions import CalibrationBinDefinition, CalibrationSpec
from afre.calibration.isotonic import isotonic_probability, pav
from afre.calibration.schema import CalibrationMethod, EmptyBinPolicy
from afre.probabilistic.definitions import ThresholdRequest
from afre.probabilistic.thresholds import event_outcome
from afre.schema import require
from afre.statistical_models.linear_algebra import finite, total


def bin_index(edges: tuple[float, ...], probability: float) -> int:
    require(0 <= finite(probability) <= 1, "bin probability domain")
    for i, upper in enumerate(edges[1:]):
        if probability < upper:
            return i
    return len(edges) - 2


def binned(
    pairs: tuple[tuple[float, bool, str], ...], definition: CalibrationBinDefinition
) -> tuple[ProbabilityBin, ...]:
    groups: list[list[tuple[float, bool, str]]] = [[] for _ in definition.edges[1:]]
    for p in sorted(pairs, key=lambda p: (p[0], p[2])):
        require(type(p[1]) is bool, "binary bin outcome")
        groups[bin_index(definition.edges, p[0])].append(p)
    result = []
    for i, group in enumerate(groups):
        count = len(group)
        sufficient = count >= definition.minimum_count
        require(
            sufficient or definition.empty_policy is EmptyBinPolicy.RAW,
            "insufficient bin count",
        )
        frequency = sum(y for _, y, _ in group) / count if count else None
        result.append(
            ProbabilityBin(
                definition.edges[i],
                definition.edges[i + 1],
                count,
                total([p for p, _, _ in group]) / count if count else None,
                frequency,
                frequency if sufficient else None,
                tuple(sorted(p[2] for p in group)),
            )
        )
    return tuple(result)


def mapping_for(
    spec: CalibrationSpec, observations: CalibrationObservationSet, event: ThresholdRequest
) -> ProbabilityMapping:
    require(event in spec.events.requests, "event not declared by calibration spec")
    pairs = tuple(
        (
            next(p.probability for p in row.probabilities if p.request == event),
            event_outcome(row.truth, event),
            row.fingerprint,
        )
        for row in observations.rows
    )
    if spec.method is CalibrationMethod.ISOTONIC_PROBABILITY:
        return ProbabilityMapping(
            spec.fingerprint, observations.fingerprint, event, spec.method, pav(pairs)
        )
    require(
        spec.method is CalibrationMethod.BINNED_PROBABILITY, "method has no probability mapping"
    )
    return ProbabilityMapping(
        spec.fingerprint,
        observations.fingerprint,
        event,
        spec.method,
        bins=binned(pairs, spec.bins),
    )


def mapped_probability(
    mapping: ProbabilityMapping, event: ThresholdRequest, probability: float
) -> float:
    require(event == mapping.event, "calibration threshold/comparison identity mismatch")
    if mapping.method is CalibrationMethod.ISOTONIC_PROBABILITY:
        return isotonic_probability(mapping.blocks, probability)
    edges = (mapping.bins[0].lower, *(b.upper for b in mapping.bins))
    value = mapping.bins[bin_index(edges, probability)].calibrated_probability
    return probability if value is None else value
