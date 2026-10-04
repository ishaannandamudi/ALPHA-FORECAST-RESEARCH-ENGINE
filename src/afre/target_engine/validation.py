"""Pure label eligibility, separate from feature admissibility and split generation."""

from afre.features import DataQuality, MissingState
from afre.target_engine.models import TargetVintage
from afre.target_engine.schema import TargetQualityFlag
from afre.time import validate_timestamp


def target_known_by_cutoff(target: TargetVintage, training_cutoff_ns: int) -> bool:
    validate_timestamp(training_cutoff_ns)
    return (
        target.state is MissingState.PRESENT
        and target.value is not None
        and target.window is not None
        and target.completion_ns is not None
        and target.origin.timestamp_ns < training_cutoff_ns
        and target.window.end_ns <= training_cutoff_ns
        and target.completion_ns <= training_cutoff_ns
        and target.clocks.final_available_ns <= training_cutoff_ns
        and target.quality.source_quality is DataQuality.VERIFIED
        and TargetQualityFlag.PARTIAL_PATH not in target.quality.flags
    )
