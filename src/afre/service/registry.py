"""Closed native artifact categories and exact metadata derivation."""

from typing import TYPE_CHECKING

from afre.schema import require
from afre.service.registry_entries import RegistryEntry
from afre.service.schema import RegistryCategory as C
from afre.service.snapshots import ForecastSnapshot

if TYPE_CHECKING:
    from afre.service.repository import ServiceRepository

CATEGORIES = {
    "FittedModelArtifact": C.MODEL,
    "ProbabilisticModelArtifact": C.MODEL,
    "CalibrationState": C.CALIBRATION,
    "PointForecast": C.FORECAST_ARTIFACT,
    "ProbabilisticForecast": C.FORECAST_ARTIFACT,
    "CalibratedForecast": C.CALIBRATION,
    "CrossSectionRanking": C.RANKING,
    "EventConditionedForecast": C.EVENT_CONDITIONED,
    "EventConditionedModel": C.EVENT_CONDITIONED,
    "EventReference": C.EVENT_CONDITIONED,
    "RegimeConditionedForecast": C.REGIME_CONDITIONED,
    "RegimeConditionedModel": C.REGIME_CONDITIONED,
    "RegimeSnapshot": C.REGIME_CONDITIONED,
    "GateModelArtifact": C.MIXTURE,
    "FixedGateSpec": C.MIXTURE,
    "LearnedGateSpec": C.MIXTURE,
    "MixtureForecast": C.MIXTURE,
    "NonlinearForecast": C.NONLINEAR,
    "NonlinearModelArtifact": C.NONLINEAR,
    "SequenceForecast": C.SEQUENCE,
    "SequenceModelArtifact": C.SEQUENCE,
    "ForecastUncertaintyDecomposition": C.UNCERTAINTY,
    "ProjectionArtifact": C.ORTHOGONALIZATION,
    "OrthogonalSignalValue": C.ORTHOGONALIZATION,
    "FusionArtifact": C.FUSION,
    "FusedForecast": C.FUSION,
    "ModelHealthSnapshot": C.HEALTH_SNAPSHOT,
    "ChallengeProgram": C.CHALLENGE_PROGRAM,
    "ChallengeRun": C.CHALLENGE_RUN,
    "ForecastSnapshot": C.FORECAST_SNAPSHOT,
}


def registration_for(
    repo: "ServiceRepository",
    identity: str,
    producer: str,
    target: str,
    horizon: str,
    anchor_source_id: str | None = None,
) -> RegistryEntry:
    raw = repo.raw(identity)
    name = type(raw).__name__
    require(name in CATEGORIES, "UNAVAILABLE: registry artifact category")
    from afre.service.context import ContextRequest
    from afre.service.context_builder import CONTEXT_TYPES, context_for
    from afre.service.native import native_source
    from afre.service.schema import ServiceContextKind

    anchor = anchor_source_id or (
        raw.publication.source_id if isinstance(raw, ForecastSnapshot) else identity
    )
    source = native_source(repo, anchor)
    require(
        (producer, target, horizon)
        == (source.producer_id, source.target.fingerprint, source.target.horizon.fingerprint),
        "INCOMPATIBLE: registry anchor producer/target/horizon",
    )
    if identity not in (source.artifact.fingerprint, source.producer_id) and not isinstance(
        raw, ForecastSnapshot
    ):
        kinds = tuple(k for k, names in CONTEXT_TYPES.items() if name in names)
        from afre.fusion.sources import FAMILIES

        if name == "ChallengeProgram":
            from afre.challenger.participants import ParticipantReference

            participants = tuple(
                repo.get(ParticipantReference, i)
                for i in (
                    getattr(raw, "champion_id", "missing"),
                    *getattr(raw, "challenger_ids", ()),
                )
            )
            require(
                producer in {p.reference.producer_id for p in participants},
                "INCOMPATIBLE: challenge program producer",
            )
        elif name == "ProjectionArtifact":
            # Orthogonal projections are descriptive contextual fitting metadata.
            pass
        elif identity in _anchor_nodes(repo, anchor, source.producer_id):
            pass
        elif kinds and name not in FAMILIES and name != "FusedForecast":
            kind = kinds[0]
            context_for(
                repo,
                ContextRequest(
                    kind,
                    identity,
                    kind in (ServiceContextKind.HEALTH, ServiceContextKind.CHALLENGE),
                ),
                source,
                getattr(raw, "available_ns", 0),
            )
        else:
            from afre.service.lineage import lineage_for

            graph = lineage_for(repo, anchor, (source.producer_id,))
            admitted = identity in graph.node_ids
            if not admitted and (name in FAMILIES or name == "FusedForecast"):
                peer = native_source(repo, identity)
                admitted = (
                    peer.producer_id in graph.node_ids
                    and peer.target == source.target
                    and peer.origin.timestamp_ns == source.origin.timestamp_ns
                    and peer.origin.availability_cutoff_ns
                    == source.origin.availability_cutoff_ns
                )
            require(admitted, "INCOMPATIBLE: contributing registry model")
    spec = raw
    spec_id = getattr(raw, "spec_id", getattr(getattr(raw, "inputs", None), "spec_id", None))
    if spec_id:
        spec = repo.raw(spec_id)
    native_target = getattr(spec, "target", None)
    require(
        native_target is None or native_target.fingerprint == target,
        "INCOMPATIBLE: registry target",
    )
    require(
        getattr(raw, "target_definition_id", getattr(raw, "target_id", target)) == target,
        "INCOMPATIBLE: registry exact target",
    )
    require(getattr(raw, "horizon_id", horizon) == horizon, "INCOMPATIBLE: registry horizon")
    inputs = getattr(raw, "inputs", None)
    available = getattr(
        raw, "available_ns", getattr(inputs, "available_ns", getattr(raw, "declared_ns", 0))
    )
    clocks = getattr(raw, "clocks", None)
    if clocks:
        available = clocks.final_available_ns
    cutoff = getattr(
        raw,
        "fit_cutoff_ns",
        getattr(
            raw,
            "training_cutoff_ns",
            getattr(inputs, "training_cutoff_ns", getattr(spec, "training_cutoff_ns", None)),
        ),
    )
    if isinstance(raw, ForecastSnapshot):
        available = raw.publication.published_ns
    return RegistryEntry(
        identity,
        name,
        CATEGORIES[name],
        producer,
        name,
        str(getattr(raw, "implementation_version", "1.0")),
        target,
        horizon,
        getattr(raw, "computed_ns", getattr(raw, "declared_ns", available)),
        cutoff,
        available,
        anchor,
    )


def _anchor_nodes(repo: "ServiceRepository", anchor: str, producer: str) -> tuple[str, ...]:
    from afre.service.lineage import lineage_for

    return lineage_for(repo, anchor, (producer,)).node_ids
