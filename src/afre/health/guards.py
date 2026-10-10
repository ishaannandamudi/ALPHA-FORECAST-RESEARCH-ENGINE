"""Target protection before native or health caches."""

from typing import TYPE_CHECKING

from afre.schema import Artifact, require
from afre.target_engine.models import TargetVintage

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository


def guard(repo: "HealthRepository", cls: type[Artifact], identity: str) -> None:
    if cls is TargetVintage:
        require(
            not repo._feature_only_depth,
            "health target-free monitoring cannot read TargetVintage",
        )
