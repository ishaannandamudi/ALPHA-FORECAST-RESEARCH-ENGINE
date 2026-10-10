"""Every supplied fusion opportunity maps to a native AFRE19 planned trial."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from afre.fusion.artifacts import FusedForecast, FusionArtifact
from afre.fusion.definitions import FusionSpec
from afre.multiple_testing.engine import MultipleTestingEngine
from afre.multiple_testing.families import HypothesisFamily
from afre.multiple_testing.hypotheses import HypothesisDefinition, TestAssumptions
from afre.multiple_testing.schema import (
    AdaptiveTrialStatus,
    CorrectionMethod,
    DependenceAssumption,
    HypothesisDirection,
    RawTestMethod,
    ResearchMetric,
)
from afre.multiple_testing.trials import TrialSpecification
from afre.schema import Artifact, contract, require

if TYPE_CHECKING:
    from afre.fusion.repository import FusionRepository


@contract("fus_trial_pool")
@dataclass(frozen=True, slots=True)
class FusionTrialPool(Artifact):
    spec_ids: tuple[str, ...]
    plan_ids: tuple[str, ...]
    family_id: str
    declared_ns: int
    failed_spec_ids: tuple[str, ...]

    def _normalize(self) -> None:
        object.__setattr__(self, "spec_ids", tuple(sorted(self.spec_ids)))
        object.__setattr__(self, "plan_ids", tuple(sorted(self.plan_ids)))
        object.__setattr__(self, "failed_spec_ids", tuple(sorted(self.failed_spec_ids)))

    def _validate(self) -> None:
        require(
            0 < len(self.spec_ids) == len(self.plan_ids) <= 128
            and len(set(self.spec_ids)) == len(self.spec_ids)
            and len(set(self.plan_ids)) == len(self.plan_ids)
            and set(self.failed_spec_ids) <= set(self.spec_ids),
            "complete distinct fusion opportunity pool",
        )


def register_pool(
    repo: "FusionRepository",
    bindings: tuple[tuple[str, tuple[str, ...]], ...],
    failure_anchor_ids: tuple[str, ...] = (),
) -> FusionTrialPool:
    require(
        0 < len(bindings) <= 128 and len({s for s, _ in bindings}) == len(bindings),
        "finite fusion trial pool",
    )
    specs = tuple(repo.resolve(FusionSpec, s) for s, _ in sorted(bindings))
    first = specs[0]
    require(
        all(
            (s.target_id, s.horizon_id, s.fold_id, s.dataset_id)
            == (first.target_id, first.horizon_id, first.fold_id, first.dataset_id)
            for s in specs
        ),
        "trial pool exact target/horizon/fold protocol",
    )
    engine = MultipleTestingEngine(repo)
    declared = max(s.declared_ns for s in specs)
    key = first.fingerprint[-64:]
    hypothesis = HypothesisDefinition(
        key,
        key,
        first.target_id,
        first.horizon_id,
        ResearchMetric.SQUARED_ERROR,
        0.0,
        HypothesisDirection.TWO_SIDED,
        RawTestMethod.NORMAL_MEAN,
        2,
        TestAssumptions(
            False, False, False, False, "fusion-descriptive-no-inference", declared
        ),
        declared,
    )
    engine.hypothesis(hypothesis)
    plans, failed = [], []
    for spec_id, forecast_ids in sorted(bindings):
        spec = repo.get(FusionSpec, spec_id)
        if forecast_ids:
            values = tuple(repo.resolve(FusedForecast, i) for i in sorted(forecast_ids))
            require(
                all(
                    repo.get(FusionArtifact, v.artifact_id).spec_id == spec_id
                    and v.value is not None
                    for v in values
                ),
                "exact available fusion trial sources",
            )
            source_ids = tuple(v.fingerprint for v in values)
            samples = tuple(v.sample_id for v in values)
            phase = 21
        else:
            require(
                bool(failure_anchor_ids),
                "failed fusion attempt requires explicit native protocol anchor",
            )
            from afre.uncertainty.sources import source_for

            anchors = tuple(source_for(repo, i) for i in sorted(failure_anchor_ids))
            require(
                all(type(v.artifact).__name__ == "PointForecast" for v in anchors),
                "failed opportunity point protocol anchor",
            )
            source_ids = failure_anchor_ids
            samples = tuple(v.sample_id for v in anchors)
            phase = 5
            failed.append(spec_id)
        plan = TrialSpecification(
            spec_id[-64:],
            hypothesis.fingerprint,
            phase,
            source_ids[0],
            source_ids,
            samples,
            spec.dataset_id,
            spec.fold_id,
            (),
            (spec_id,),
            (("fusion-spec", spec_id), ("failed-protocol-anchor", str(not forecast_ids))),
            declared,
            AdaptiveTrialStatus.PREDECLARED,
        )
        plans.append(engine.plan(plan))
    family = HypothesisFamily(
        key,
        tuple(p.fingerprint for p in plans),
        CorrectionMethod.HOLM,
        0.05,
        DependenceAssumption.ARBITRARY,
        declared,
        True,
    )
    engine.family(family)
    return FusionTrialPool(
        tuple(s.fingerprint for s in specs),
        tuple(p.fingerprint for p in plans),
        family.fingerprint,
        declared,
        tuple(failed),
    )
