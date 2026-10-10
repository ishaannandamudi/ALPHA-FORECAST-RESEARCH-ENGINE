"""Pinned dataset/sample provenance checks that never reconstruct a label value."""

from typing import TYPE_CHECKING

from afre.research_datasets.definitions import ResearchDatasetDefinition
from afre.research_datasets.manifests import ResearchDatasetManifest, ResearchInputBuild
from afre.research_datasets.samples import ResearchSample, ResearchSelection
from afre.schema import Artifact, require

if TYPE_CHECKING:
    from afre.selection.repository import SelectionRepository


def validate_metadata(repo: "SelectionRepository", value: Artifact) -> None:
    if isinstance(value, ResearchSample):
        build = repo.get(ResearchInputBuild, value.input_build_id)
        definition = repo.get(ResearchDatasetDefinition, build.definition_id)
        selection = repo.get(ResearchSelection, value.selection_id)
        require(
            value.selection_id in build.selection_ids
            and value.target_definition_id
            in {t.fingerprint for t in definition.target_set.definitions}
            and value.feature_set_id == definition.feature_set.fingerprint,
            "selection sample exact frozen build/target/features",
        )
        require(
            (
                value.security,
                value.origin,
                value.timestamp_ns,
                value.snapshot_id,
                value.eligibility_id,
                value.join_id,
                value.group_keys,
            )
            == (
                selection.security,
                selection.origin,
                selection.timestamp_ns,
                selection.request.snapshot_id,
                selection.eligibility_id,
                selection.join_id,
                selection.group_keys,
            ),
            "selection sample exact input provenance",
        )
        if value.target_id is not None:
            row = repo._connection.execute(
                "SELECT definition_id,origin_id,available_ns FROM target_vintages "
                "WHERE fingerprint=?",
                (value.target_id,),
            ).fetchone()
            require(
                row is not None
                and value.origin is not None
                and row
                == (
                    value.target_definition_id,
                    value.origin.fingerprint,
                    value.target_available_ns,
                ),
                "selection sample exact target metadata",
            )
    elif isinstance(value, ResearchDatasetManifest):
        build = repo.get(ResearchInputBuild, value.input_build_id)
        definition = repo.get(ResearchDatasetDefinition, value.definition_id)
        samples = tuple(repo.get(ResearchSample, i) for i in value.sample_ids)
        require(
            build.definition_id == definition.fingerprint
            and {s.input_build_id for s in samples} == {build.fingerprint}
            and {(s.selection_id, s.target_definition_id) for s in samples}
            == {
                (i, t.fingerprint)
                for i in build.selection_ids
                for t in definition.target_set.definitions
            }
            and len(samples)
            == len(build.selection_ids) * len(definition.target_set.definitions),
            "selection dataset complete pinned metadata grid",
        )
