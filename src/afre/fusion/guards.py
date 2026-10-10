"""Truth checks before any repository cache, including TRAIN response isolation."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from afre.schema import Artifact, require
from afre.target_engine.models import TargetVintage

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository


@contextmanager
def train_only(repo: "FusionRepository", target_ids: tuple[str, ...]) -> Iterator[None]:
    old = repo._fusion_train_targets
    repo._fusion_train_targets = set(target_ids)
    try:
        yield
    finally:
        repo._fusion_train_targets = old


def guard(repo: "FusionRepository", cls: type[Artifact], identity: str) -> None:
    if cls is TargetVintage:
        require(not repo._feature_only_depth, "fusion application cannot read TargetVintage")
        require(
            repo._fusion_train_targets is None or identity in repo._fusion_train_targets,
            "fusion TRAIN guard excludes VALIDATION/TEST target",
        )
    if repo._fusion_train_targets is not None:
        require(
            cls.__name__
            not in {
                "ResearchTrial",
                "CandidateValidationResult",
                "SelectionResult",
                "FusionComparison",
                "DiversityMatrix",
                "TestEvaluation",
                "PointEvaluation",
                "ProbabilisticEvaluation",
                "FamilyAnalysis",
            },
            "fusion TRAIN fit cannot inspect held-out evaluation/selection",
        )
