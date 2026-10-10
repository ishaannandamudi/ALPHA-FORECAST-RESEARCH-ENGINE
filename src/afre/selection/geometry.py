"""Native purge/embargo geometry replay without decoding any target value.

TRAIN admission is checked from pinned native availability indexes here; native
model fitting subsequently verifies the full TRAIN target contract.
"""

from typing import TYPE_CHECKING

from afre.research_datasets.intervals import IntervalIndex, SampleInformationInterval
from afre.research_datasets.materialization import BLOCKED_STATES
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition, PurgeRule
from afre.research_datasets.splits import FoldDefinition, FoldMembership, SplitDefinition
from afre.research_datasets.splitting import embargo_intervals, group_for, interval_for
from afre.schema import require

if TYPE_CHECKING:
    from afre.research_datasets.repository import DatasetRepository


def training_metadata_known(repo: "DatasetRepository", sample: ResearchSample, at: int) -> bool:
    row = repo._connection.execute(
        (
            "SELECT origin_ns,end_ns,available_ns,state,quality FROM "
            "target_vintages WHERE fingerprint=?"
        ),
        (sample.target_id,),
    ).fetchone()
    return (
        row is not None
        and row[0] < at
        and row[1] is not None
        and row[1] <= at
        and row[2] <= at
        and row[3] == "present"
        and row[4] == "verified"
    )


def metadata_memberships_for(
    repo: "DatasetRepository",
    fold: FoldDefinition,
    definition: SplitDefinition,
    samples: tuple[ResearchSample, ...],
    folds: tuple[FoldDefinition, ...],
) -> tuple[FoldMembership, ...]:
    protected: dict[str, list[SampleInformationInterval]] = {}
    embargo = IntervalIndex(embargo_intervals(repo, definition, folds))
    purge = definition.purge
    if purge.rule is not PurgeRule.NONE:
        for sample in samples:
            if (
                (
                    fold.validation.contains(sample.timestamp_ns)
                    or (fold.test is not None and fold.test.contains(sample.timestamp_ns))
                )
                and sample.state not in BLOCKED_STATES
                and not sample.dropped
            ):
                interval = interval_for(sample, purge.rule)
                require(
                    interval is not None, "protected sample has unresolved information interval"
                )
                assert interval is not None
                protected.setdefault(group_for(sample, purge.scope), []).append(interval)
    indexes = {key: IntervalIndex(tuple(values)) for key, values in protected.items()}
    parent_ids: set[str] | None = None
    if definition.parent_fold_id is not None:
        parent_ids = {
            s.fingerprint
            for s in repo.partition_samples(definition.parent_fold_id, Partition.TRAIN)
        }
    memberships = []
    comparisons = 0
    for sample in samples:
        partition, reason = Partition.INELIGIBLE, "outside declared temporal windows"
        if sample.state in BLOCKED_STATES or sample.dropped:
            reason = "dropped sample" if sample.dropped else sample.state.value
        elif parent_ids is not None and repo.identity(sample) not in parent_ids:
            reason = "outside parent TRAIN boundary"
        elif fold.test is not None and fold.test.contains(sample.timestamp_ns):
            partition, reason = (
                Partition.TEST,
                "sealed holdout origin; truth queried separately",
            )
        elif fold.validation.contains(sample.timestamp_ns):
            partition, reason = (
                Partition.VALIDATION,
                "validation origin; truth queried separately",
            )
        elif fold.train.contains(sample.timestamp_ns):
            interval = interval_for(sample, purge.rule)
            index = (
                indexes.get(group_for(sample, purge.scope))
                if purge.rule is not PurgeRule.NONE
                else None
            )
            before = index.comparisons if index else 0
            overlap = index is not None and interval is not None and index.overlaps(interval)
            comparisons += (index.comparisons - before) if index else 0
            if overlap:
                partition, reason = Partition.PURGED, "protected information interval overlaps"
            else:
                point = SampleInformationInterval(
                    sample.timestamp_ns, sample.timestamp_ns, True, True
                )
                before = embargo.comparisons
                in_embargo = embargo.overlaps(point)
                comparisons += embargo.comparisons - before
                if in_embargo:
                    partition, reason = (
                        Partition.EMBARGOED,
                        "origin inside declared embargo fence",
                    )
                elif sample.target_id is None or not training_metadata_known(
                    repo, sample, fold.training_cutoff_ns
                ):
                    reason = "target not known by training cutoff"
                else:
                    partition, reason = (
                        Partition.TRAIN,
                        "causal inputs and label known by training cutoff",
                    )
        require(
            comparisons <= repo.dataset_bounds.interval_comparisons, "interval comparison bound"
        )
        memberships.append(
            FoldMembership(repo.identity(fold), repo.identity(sample), partition, reason)
        )
    repo.last_interval_comparisons = comparisons
    return tuple(memberships)
