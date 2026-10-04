"""AFRE-4 causal research samples, leakage-safe temporal folds and train-only statistics."""

from afre.research_datasets.audits import ContaminationAudit, SampleContaminationAudit
from afre.research_datasets.definitions import (
    DatasetCompatibility,
    ResearchDatasetDefinition,
    ResearchGroupBinding,
    ResearchOriginRequest,
)
from afre.research_datasets.engine import DatasetEngine
from afre.research_datasets.intervals import SampleInformationInterval
from afre.research_datasets.manifests import (
    DatasetColumn,
    DatasetColumnManifest,
    ResearchDatasetManifest,
    ResearchInputBuild,
)
from afre.research_datasets.preprocessing import (
    FoldPreprocessingSpec,
    FoldPreprocessingState,
    apply_state,
)
from afre.research_datasets.repository import DatasetRepository
from afre.research_datasets.samples import ResearchSample, ResearchSelection
from afre.research_datasets.schema import (
    ColumnRole,
    DatasetBounds,
    DatasetCompleteness,
    DatasetMissingPolicy,
    EmbargoBasis,
    EmbargoDirection,
    Partition,
    PreprocessingScope,
    PurgeRule,
    PurgeScope,
    SampleState,
    SplitStrategy,
    ZeroScaleRule,
)
from afre.research_datasets.splits import (
    EmbargoBarGrid,
    EmbargoPolicy,
    FoldDefinition,
    FoldMembership,
    PurgePolicy,
    ResearchSplit,
    SplitDefinition,
    TestEvaluation,
)

__all__ = [
    "ContaminationAudit",
    "SampleContaminationAudit",
    "DatasetCompatibility",
    "ResearchDatasetDefinition",
    "ResearchGroupBinding",
    "ResearchOriginRequest",
    "DatasetEngine",
    "SampleInformationInterval",
    "DatasetColumn",
    "DatasetColumnManifest",
    "ResearchDatasetManifest",
    "ResearchInputBuild",
    "FoldPreprocessingSpec",
    "FoldPreprocessingState",
    "apply_state",
    "DatasetRepository",
    "ResearchSample",
    "ResearchSelection",
    "ColumnRole",
    "DatasetBounds",
    "DatasetCompleteness",
    "DatasetMissingPolicy",
    "EmbargoBasis",
    "EmbargoDirection",
    "Partition",
    "PreprocessingScope",
    "PurgeRule",
    "PurgeScope",
    "SampleState",
    "SplitStrategy",
    "ZeroScaleRule",
    "EmbargoBarGrid",
    "EmbargoPolicy",
    "FoldDefinition",
    "FoldMembership",
    "PurgePolicy",
    "ResearchSplit",
    "SplitDefinition",
    "TestEvaluation",
]
