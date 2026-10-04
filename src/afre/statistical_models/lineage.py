"""Static upstream edges allow one shared model/feature/target depth budget."""

from typing import TYPE_CHECKING

from afre.feature_store.materialization import FeatureComputationReceipt
from afre.feature_store.models import FeatureVintage, SourceReference
from afre.feature_store.normalization import NormalizationState
from afre.feature_store.providers import MarketBar
from afre.schema import Artifact, require
from afre.target_engine.corporate_actions import TargetActionStream, TargetCorporateAction
from afre.target_engine.definitions import TargetDefinition
from afre.target_engine.market_data import TargetBar, TargetMarketSource, TargetSourceBuild
from afre.target_engine.models import TargetVintage
from afre.target_engine.residuals import SuppliedBenchmarkReturn
from afre.universe.validation import lineage_edges as universe_edges

if TYPE_CHECKING:
    from afre.statistical_models.repository import ModelRepository


def upstream_edges(repo: "ModelRepository", value: Artifact) -> tuple[str, ...]:
    edges = universe_edges(value)
    if edges:
        return edges
    if isinstance(value, SourceReference):
        return (
            *value.parent_source_ids,
            *(
                (value.provenance.artifact_id,)
                if value.provenance.artifact_id.startswith("afre.fs_market_bar:")
                else ()
            ),
        )
    if isinstance(value, MarketBar):
        return (value.source.fingerprint,)
    if isinstance(value, FeatureVintage):
        edges = (value.source.fingerprint, *value.input_ids)
        edges += tuple(
            item
            for item in (
                value.predecessor_id,
                value.normalization_state_id,
                value.computation_spec_id,
            )
            if item is not None
        )
        if value.computation_spec_id is not None:
            receipt = repo.receipt_for(value.fingerprint)
            require(receipt is not None, "computed model feature lacks a computation receipt")
            assert receipt is not None
            edges += (receipt.fingerprint,)
        return edges
    if isinstance(value, NormalizationState):
        return value.fit_sample_ids
    if isinstance(value, FeatureComputationReceipt):
        return value.input_ids
    if isinstance(value, TargetVintage):
        return (
            value.definition.fingerprint,
            value.source_build_id,
            *value.path_ids,
            *value.action_ids,
            *(
                item
                for item in (value.origin_bar_id, value.endpoint_bar_id, value.benchmark_id)
                if item is not None
            ),
        )
    if isinstance(value, TargetSourceBuild):
        return (
            value.source.fingerprint,
            value.calendar.fingerprint,
            *((value.action_stream.fingerprint,) if value.action_stream else ()),
        )
    if isinstance(value, TargetMarketSource):
        return (value.upstream.fingerprint,)
    if isinstance(value, TargetBar):
        return (
            value.source.fingerprint,
            *((value.predecessor_id,) if value.predecessor_id else ()),
        )
    if isinstance(value, TargetActionStream):
        return value.action_ids
    if isinstance(value, (TargetCorporateAction, SuppliedBenchmarkReturn)):
        return (
            *((value.predecessor_id,) if value.predecessor_id else ()),
            *(
                (value.benchmark.fingerprint,)
                if isinstance(value, SuppliedBenchmarkReturn)
                else ()
            ),
        )
    if isinstance(value, TargetDefinition) and value.benchmark is not None:
        return (value.benchmark.fingerprint,)
    return ()
