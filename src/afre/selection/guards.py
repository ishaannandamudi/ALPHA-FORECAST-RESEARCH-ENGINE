"""Repository guards before caches; no held-out response access during fitting."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, require
from afre.selection.definitions import SearchSpace
from afre.selection.schema import SelectionReadRole
from afre.target_engine.models import TargetVintage

if TYPE_CHECKING:
    from afre.selection.repository import SelectionRepository


@contextmanager
def read_role(
    repo: "SelectionRepository", role: SelectionReadRole, space: SearchSpace
) -> Iterator[None]:
    old = repo._selection_role, repo._selection_space, repo._selection_targets
    targets: set[str] = set()
    sealed = {
        row[0]
        for row in repo._connection.execute(
            "SELECT m.sample_id FROM r_memberships m JOIN r_folds f ON m.fold_id=f.fingerprint "
            "WHERE f.dataset_id=? AND m.partition=?",
            (space.dataset_id, Partition.TEST.value),
        )
    }
    if role is not SelectionReadRole.PLANNING:
        allowed = (
            (Partition.TRAIN,)
            if role is SelectionReadRole.FIT
            else (Partition.TRAIN, Partition.VALIDATION)
        )
        for part in allowed:
            for sample in repo.partition_samples(space.fold_id, part):
                if (
                    sample.target_definition_id == space.target_id
                    and sample.fingerprint not in sealed
                    and sample.origin is not None
                    and (
                        part is Partition.TRAIN
                        or sample.fingerprint in space.validation_sample_ids
                    )
                ):
                    targets.add(sample.origin.fingerprint)
    repo._selection_role, repo._selection_space, repo._selection_targets = role, space, targets
    try:
        if role is SelectionReadRole.PLANNING:
            with repo.feature_only():
                yield
        else:
            yield
    finally:
        repo._selection_role, repo._selection_space, repo._selection_targets = old


def guard_identity(repo: "SelectionRepository", cls: type[Artifact], identity: str) -> None:
    role = repo._selection_role
    if role is None:
        return
    require(
        cls.__name__
        not in {
            "PointEvaluation",
            "ProbabilisticEvaluation",
            "CalibrationEvaluation",
            "EventConditionedEvaluation",
            "RegimeConditionedEvaluation",
            "MixtureEvaluation",
            "NonlinearEvaluation",
            "SequenceEvaluation",
            "UncertaintyEvaluation",
            "StabilityEvaluation",
            "CostEvaluation",
            "TestEvaluation",
        },
        "selection cannot inspect native held-out evaluation payloads",
    )
    if role is SelectionReadRole.FIT:
        require(
            cls.__name__
            not in {
                "CandidateValidationResult",
                "SelectionResult",
                "CandidateRegistrySnapshot",
                "SelectionAudit",
                "CandidateComparison",
                "ResearchTrial",
                "EffectSizeResult",
                "PValueResult",
                "FamilyAnalysis",
                "AdjustedHypothesisResult",
            },
            "TRAIN fitting cannot inspect held-out selection/results",
        )
    if cls.__name__ == "ResearchTrial":
        require(
            repo._connection.execute(
                "SELECT 1 FROM mt_test_uses WHERE fingerprint=?", (identity,)
            ).fetchone()
            is None,
            "selection cannot inspect TEST trial responses",
        )
    if cls is TargetVintage:
        require(role is not SelectionReadRole.PLANNING, "selection planning cannot read truth")
        row = repo._connection.execute(
            "SELECT origin_id,definition_id FROM target_vintages WHERE fingerprint=?",
            (identity,),
        ).fetchone()
        require(
            row is not None
            and repo._selection_space is not None
            and row[0] in repo._selection_targets
            and row[1] == repo._selection_space.target_id,
            "selection response guard: TEST/held-out truth excluded",
        )
    if cls.__name__ in {
        "TestEvaluation",
        "TrialRegistrySnapshot",
        "TestReuseDiagnostic",
        "TargetDatasetManifest",
        "TargetAudit",
    }:
        require(False, "selection cannot inspect TEST-bearing evidence")
    if role is SelectionReadRole.PLANNING:
        require(
            cls.__name__
            not in {
                "DesignMatrix",
                "TrainingMatrixRow",
                "InteractionMatrix",
                "InteractionTrainingRow",
                "SequenceDataset",
                "SequenceTrainingRow",
                "PointEvaluation",
                "ProbabilisticEvaluation",
                "ResearchTrial",
                "EffectSizeResult",
                "CandidateValidationResult",
                "SelectionResult",
                "CandidateRegistrySnapshot",
            },
            "selection planning cannot read response/results",
        )


def guard_value(repo: "SelectionRepository", value: Artifact) -> None:
    if repo._selection_role is None:
        return
    # Native metadata objects may include the full split geometry. Numeric truth
    # is independently guarded by origin BEFORE decoding a TargetVintage.
    if isinstance(value, ResearchSample):
        return
    if type(value).__name__ in {
        "TrainingMatrixRow",
        "InteractionTrainingRow",
        "SequenceTrainingRow",
    }:
        space = repo._selection_space
        assert space is not None
        allowed = {
            s.fingerprint for s in repo.partition_samples(space.fold_id, Partition.TRAIN)
        }
        require(
            getattr(value, "sample_id", None) in allowed, "selection TRAIN response-row guard"
        )
    scope = getattr(value, "scope", getattr(getattr(value, "input", None), "scope", None))
    require(
        getattr(scope, "value", None) != "test",
        "selection cannot inspect TEST forecast/evaluation",
    )
    require(
        not getattr(value, "test_seal_ids", ())
        and getattr(value, "test_evaluation_id", None) is None,
        "selection cannot inspect sealed TEST results",
    )
