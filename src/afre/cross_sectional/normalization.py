"""Origin-local peer transforms, distinct from learned TRAIN preprocessing."""

import math
from statistics import median

from afre.cross_sectional.artifacts import PeerState, RawScore
from afre.cross_sectional.definitions import CrossSectionSpec
from afre.cross_sectional.groups import GroupMembership
from afre.cross_sectional.ranks import rank_values
from afre.cross_sectional.schema import (
    CrossSectionQuality,
    CrossSectionScoreState,
    PeerTransform,
    SmallGroupPolicy,
)
from afre.schema import require
from afre.statistical_models.linear_algebra import finite, total


def average(values: tuple[float, ...]) -> float:
    require(bool(values), "empty mean")
    return finite(values[0] + total([finite(v - values[0]) for v in values]) / len(values))


def peer_state(
    spec: CrossSectionSpec,
    scores: tuple[RawScore, ...],
    computed_ns: int,
    groups: tuple[GroupMembership, ...] = (),
    group_neutral: bool = False,
) -> PeerState:
    admitted = tuple(
        sorted((s.security.fingerprint, s.value) for s in scores if s.value is not None)
    )
    require(
        all(
            s.available_ns is None or s.available_ns <= computed_ns
            for s in scores
            if s.state is CrossSectionScoreState.AVAILABLE
        ),
        "future peer computation",
    )
    n = len(admitted)
    quality = (
        CrossSectionQuality.UNAVAILABLE
        if not n
        else CrossSectionQuality.TOO_SMALL
        if n < spec.normalization.minimum_count
        else CrossSectionQuality.CONSTANT
        if len({v for _, v in admitted}) == 1
        else CrossSectionQuality.VALID
    )
    center = scale = None
    statistics: list[tuple[str, int, float | None]] = []
    unavailable: list[str] = []
    values: tuple[tuple[str, float], ...] = ()
    if group_neutral:
        policy = spec.group
        require(policy is not None, "group peer state requires policy")
        assert policy is not None
        by_security = {g.security.fingerprint: g for g in groups}
        grouped: dict[str, list[tuple[str, float]]] = {}
        for security, value in admitted:
            g = by_security.get(security)
            if g is None:
                require(policy.small_group is not SmallGroupPolicy.FAIL, "missing group")
                unavailable.append(security)
            else:
                require(
                    g.matches(
                        policy,
                        spec.identity.anchor_origin.timestamp_ns,
                        spec.identity.anchor_origin.availability_cutoff_ns,
                    ),
                    "future/invalid group peer",
                )
                grouped.setdefault(g.group_id, []).append((security, value))
        output: list[tuple[str, float]] = []
        for key, peers in sorted(grouped.items()):
            mean = average(tuple(v for _, v in peers))
            small = len(peers) < policy.minimum_count
            statistics.append((key, len(peers), mean))
            if small:
                require(policy.small_group is not SmallGroupPolicy.FAIL, "small group")
            if small and policy.small_group is SmallGroupPolicy.MARK_UNAVAILABLE:
                unavailable.extend(k for k, _ in peers)
            else:
                output.extend((k, v if small else finite(v - mean)) for k, v in peers)
        values = tuple(output)
    elif n >= spec.normalization.minimum_count:
        policy_n = spec.normalization
        x = tuple(v for _, v in admitted)
        if policy_n.transform is PeerTransform.NONE:
            values = admitted
        elif policy_n.transform is PeerTransform.PERCENTILE:
            values = tuple(
                (k, p) for k, _, p in rank_values(admitted, spec.direction, spec.ties)
            )
        else:
            center = (
                float(median(x))
                if policy_n.transform is PeerTransform.MEDIAN_MAD
                else average(x)
            )
            centered = tuple(finite(v - center) for v in x)
            scale = (
                finite(float(median(tuple(abs(v) for v in centered))) * policy_n.mad_scale)
                if policy_n.transform is PeerTransform.MEDIAN_MAD
                else finite(math.hypot(*centered) / math.sqrt(n - policy_n.sample_denominator))
            )
            if scale == 0:
                quality = CrossSectionQuality.CONSTANT
            values = tuple(
                (k, finite(v / scale) if scale else 0.0)
                for (k, _), v in zip(admitted, centered, strict=True)
            )
    return PeerState(
        spec.fingerprint,
        tuple(s.fingerprint for s in scores),
        values,
        center,
        scale,
        tuple(statistics),
        tuple(unavailable),
        quality,
        computed_ns,
        group_neutral,
    )
