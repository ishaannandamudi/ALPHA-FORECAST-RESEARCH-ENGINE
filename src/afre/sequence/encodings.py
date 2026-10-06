"""Exact causal irregular time encodings, with no invented grid or interpolation."""

from afre.sequence.schema import SequenceTimeEncoding


def encode_times(
    times: tuple[int, ...], cutoff_ns: int, encoding: SequenceTimeEncoding
) -> tuple[float, ...]:
    if encoding is SequenceTimeEncoding.DELTA_SECONDS:
        return tuple(0.0 if i == 0 else (t - times[i - 1]) / 1e9 for i, t in enumerate(times))
    if encoding is SequenceTimeEncoding.AGE_FROM_ORIGIN:
        return tuple((cutoff_ns - t) / 1e9 for t in times)
    if encoding is SequenceTimeEncoding.NORMALIZED_POSITION:
        return tuple(i / (len(times) - 1) if len(times) > 1 else 0.0 for i in range(len(times)))
    return (0.0,) * len(times)
