"""UTC nanoseconds and exact half-open research ranges."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from afre.schema import Artifact, contract, require

MAX_TIMESTAMP_NS = 2**63 - 1
SECOND_NS = 1_000_000_000
DAY_NS = 86_400 * SECOND_NS
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def validate_timestamp(value: int) -> None:
    require(type(value) is int and 0 <= value <= MAX_TIMESTAMP_NS, "invalid UTC nanoseconds")


def datetime_to_ns(value: datetime) -> int:
    require(value.tzinfo is not None and value.utcoffset() is not None, "naive datetime")
    delta = value.astimezone(UTC) - EPOCH
    result = (delta.days * 86_400 + delta.seconds) * SECOND_NS + delta.microseconds * 1000
    validate_timestamp(result)
    return result


def ns_to_datetime(value: int) -> datetime:
    validate_timestamp(value)
    require(value % 1000 == 0, "datetime conversion would lose nanoseconds")
    return EPOCH + timedelta(microseconds=value // 1000)


@contract("time_range")
@dataclass(frozen=True, slots=True)
class TimeRange(Artifact):
    start_ns: int
    end_ns: int

    def _validate(self) -> None:
        require(self.start_ns < self.end_ns, "empty or reversed time range")

    def contains(self, timestamp_ns: int) -> bool:
        validate_timestamp(timestamp_ns)
        return self.start_ns <= timestamp_ns < self.end_ns
