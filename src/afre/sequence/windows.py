"""Cutoff-first revisions, exact timestamp alignment and explicit masked padding."""

from typing import TYPE_CHECKING

from afre.forecast import ForecastOrigin
from afre.schema import require
from afre.sequence.artifacts import SequenceObservation, SequenceSnapshot
from afre.sequence.definitions import SequenceFeatureDefinition, SequenceWindowSpec
from afre.sequence.encodings import encode_times
from afre.sequence.schema import (
    SequenceCompleteness,
    SequencePadding,
    SequenceRevisionPolicy,
    SequenceWindowMode,
)

if TYPE_CHECKING:
    from afre.sequence.repository import SequenceRepository


def snapshot_for(
    repo: "SequenceRepository",
    origin: ForecastOrigin,
    features: tuple[SequenceFeatureDefinition, ...],
    window: SequenceWindowSpec,
    candidate_ids: tuple[str, ...],
    computed_ns: int,
) -> SequenceSnapshot:
    b = repo.sequence_bounds
    require(
        0 < len(features) <= b.features
        and window.maximum_observations <= b.length
        and len(candidate_ids) <= b.observations
        and len(set(candidate_ids)) == len(candidate_ids),
        "sequence extraction bounds/duplicates",
    )
    features = tuple(sorted(features, key=lambda f: f.fingerprint))
    feature_ids = tuple(f.fingerprint for f in features)
    require(len(set(feature_ids)) == len(feature_ids), "unique sequence feature definitions")
    if window.revision_policy is SequenceRevisionPolicy.EXACT_VINTAGE:
        require(
            tuple(sorted(candidate_ids)) == window.exact_observation_ids,
            "exact vintage candidates",
        )
    cutoff = origin.availability_cutoff_ns
    lower = cutoff - window.duration_ns if window.duration_ns is not None else None
    groups: dict[tuple[str, int], list[SequenceObservation]] = {}
    exclusions: list[tuple[str, str]] = []
    for identity in sorted(candidate_ids):
        value = repo.resolve(SequenceObservation, identity)
        repo._validate_links(value)
        require(
            computed_ns >= max(value.available_ns, value.afre_ready_ns),
            "snapshot candidate evidence unavailable at construction",
        )
        require(
            value.security == origin.instrument and value.feature_id in feature_ids,
            "sequence candidate security/feature mismatch",
        )
        reason = None
        if value.available_ns > cutoff:
            reason = "future-availability"
        elif value.observation_ns > cutoff or (
            value.observation_ns == cutoff and not window.upper_inclusive
        ):
            reason = "future-or-open-upper-observation"
        elif lower is not None and (
            value.observation_ns < lower
            or value.observation_ns == lower
            and not window.lower_inclusive
        ):
            reason = "outside-lower-window"
        if reason:
            exclusions.append((identity, reason))
        else:
            groups.setdefault((value.feature_id, value.observation_ns), []).append(value)
    selected: dict[tuple[str, int], SequenceObservation] = {}
    for key, revisions in sorted(groups.items()):
        require(
            len(revisions) == 1
            or window.revision_policy is SequenceRevisionPolicy.LATEST_AVAILABLE_REVISION,
            "multiple semantic observations require explicit latest policy",
        )
        chosen = max(revisions, key=lambda v: (v.available_ns, v.revision_id, v.fingerprint))
        selected[key] = chosen
        exclusions.extend(
            (v.fingerprint, "superseded-available-revision") for v in revisions if v != chosen
        )
    times = tuple(sorted({t for _, t in selected}))[-window.maximum_observations :]
    keep = set(times)
    exclusions.extend(
        (v.fingerprint, "bounded-latest-window")
        for (_, t), v in selected.items()
        if t not in keep
    )
    rows = tuple(tuple(selected.get((f, t)) for f in feature_ids) for t in times)
    ids = tuple(tuple(v.fingerprint if v else None for v in row) for row in rows)
    values = tuple(tuple(v.value if v else None for v in row) for row in rows)
    masks = tuple(tuple(v is not None for v in row) for row in values)
    counts = tuple(sum(row[j] for row in masks) for j in range(len(features)))
    real_count = sum(any(row) for row in masks)
    required = (
        window.maximum_observations
        if window.mode is SequenceWindowMode.FIXED_OBSERVATION_COUNT
        else window.minimum_observations
    )
    if window.padding is SequencePadding.FAIL_IF_SHORT:
        require(real_count >= required, "insufficient sequence history; FAIL_IF_SHORT")
    length = (
        window.maximum_observations
        if window.padding is not SequencePadding.FAIL_IF_SHORT
        else max(len(times), 1)
    )
    padding = length - len(times)
    placeholder = (None,) * len(features)
    mask_placeholder = (False,) * len(features)
    pad_values = (placeholder,) * padding
    pad_masks = (mask_placeholder,) * padding
    pad_times = (None,) * padding
    encodings: tuple[float | None, ...] = encode_times(times, cutoff, window.time_encoding)
    padded_times: tuple[int | None, ...] = times
    if window.padding is SequencePadding.RIGHT_PAD_MASKED:
        values, masks, ids = (*values, *pad_values), (*masks, *pad_masks), (*ids, *pad_values)
        padded_times, encodings = (*padded_times, *pad_times), (*encodings, *pad_times)
    else:
        values, masks, ids = (*pad_values, *values), (*pad_masks, *masks), (*pad_values, *ids)
        padded_times, encodings = (*pad_times, *padded_times), (*pad_times, *encodings)
    state = (
        SequenceCompleteness.UNAVAILABLE
        if not times
        else SequenceCompleteness.INSUFFICIENT
        if real_count < window.minimum_observations
        else SequenceCompleteness.PARTIAL
        if padding or not all(all(row) for row in masks)
        else SequenceCompleteness.COMPLETE
    )
    available = max((v.available_ns for row in rows for v in row if v), default=0)
    require(computed_ns >= available, "snapshot actual computation precedes selected input")
    exclusions.extend(
        (v.fingerprint, v.quality_state.value + "-source")
        for row in rows
        for v in row
        if v and v.missing
    )
    return SequenceSnapshot(
        origin,
        feature_ids,
        window.fingerprint,
        candidate_ids,
        ids,
        padded_times,
        values,
        masks,
        encodings,
        state,
        tuple(exclusions),
        counts,
        (cutoff - times[0]) / 1e9 if times else None,
        (cutoff - times[-1]) / 1e9 if times else None,
        tuple((b - a) / 1e9 for a, b in zip(times, times[1:], strict=False)),
        1 - sum(counts) / (length * len(features)),
        computed_ns,
        computed_ns,
    )
