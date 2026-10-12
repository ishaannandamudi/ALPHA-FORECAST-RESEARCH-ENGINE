"""Build one immutable publication under mandatory target protection."""

from typing import TYPE_CHECKING

from afre.challenger.artifacts import ChallengeRun
from afre.schema import require
from afre.service.context_builder import context_for
from afre.service.lineage import lineage_for
from afre.service.native import native_source
from afre.service.queries import SnapshotPublication
from afre.service.registry import registration_for
from afre.service.registry_entries import RegistryEntry
from afre.service.schema import SnapshotMode
from afre.service.snapshots import ForecastSnapshot
from afre.version import ENGINE_VERSION

if TYPE_CHECKING:
    from afre.service.repository import ServiceRepository


def build_snapshot(
    repo: "ServiceRepository",
    request: SnapshotPublication,
    *,
    engine_version: str = ENGINE_VERSION,
) -> tuple[ForecastSnapshot, tuple[RegistryEntry, ...]]:
    require(repo._feature_only_depth > 0, "snapshot requires target-free guard")
    source = native_source(repo, request.source_id)
    require(len(request.contexts) <= repo.service_bounds.contexts, "snapshot context bound")
    contexts = tuple(
        context_for(repo, c, source, request.published_ns) for c in request.contexts
    )
    output = source.output
    if output.probability:
        require(
            len(output.probability.components) <= repo.service_bounds.components
            and sum(len(c.atoms) for c in output.probability.components)
            <= repo.service_bounds.atoms,
            "public law component/atom bound",
        )
    program_ids = tuple(
        repo.get(ChallengeRun, c.artifact_id).program_id
        for c in contexts
        if c.kind.value == "CHALLENGE"
    )
    lineage = lineage_for(
        repo,
        request.source_id,
        (
            source.producer_id,
            source.sample.fingerprint,
            source.target.fingerprint,
            source.sample.snapshot_id,
            *(c.artifact_id for c in contexts),
            *program_ids,
        ),
    )
    from afre.service.registry import CATEGORIES

    identities = tuple(
        sorted(
            {
                request.source_id,
                source.producer_id,
                *(c.artifact_id for c in contexts),
                *(i for i in lineage.node_ids if type(repo.raw(i)).__name__ in CATEGORIES),
            }
        )
    )
    entries = tuple(
        registration_for(
            repo,
            i,
            source.producer_id,
            source.target.fingerprint,
            source.target.horizon.fingerprint,
            request.source_id,
        )
        for i in identities
    )
    models = tuple(
        i
        for i in identities
        if "Model" in type(repo.raw(i)).__name__
        or type(repo.raw(i)).__name__
        in ("FusionArtifact", "CalibrationState", "FixedGateSpec", "LearnedGateSpec")
    )
    final = max(
        (
            output.available_ns,
            *(c.available_ns for c in contexts if not c.historical_evaluation),
        )
    )
    snapshot = ForecastSnapshot(
        request,
        source.security,
        source.origin,
        source.target,
        source.producer_id,
        tuple(sorted(set((*models, source.producer_id)))),
        (request.source_id,),
        source.sample.snapshot_id,
        output,
        contexts,
        tuple(e.fingerprint for e in entries),
        lineage,
        final,
        SnapshotMode.QUALIFIED_RECONSTRUCTED
        if lineage.reconstruction_evidence_ids
        else SnapshotMode.RECORDED_CAUSAL,
        engine_version=engine_version,
    )
    return snapshot, entries
