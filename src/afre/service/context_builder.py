"""Exact compatible context projections; evaluation leaves never expand into truth."""

from dataclasses import fields
from enum import Enum
from typing import TYPE_CHECKING, cast

from afre.challenger.artifacts import ChallengeRun, PromotionAssessment, RollbackAssessment
from afre.challenger.participants import ParticipantReference
from afre.challenger.programs import ChallengeProgram
from afre.cross_sectional.artifacts import CrossSectionObservation, CrossSectionRanking
from afre.cross_sectional.definitions import CrossSectionSpec
from afre.health.artifacts import HealthMetric, ModelHealthSnapshot
from afre.health.definitions import HealthSpec, MonitoredArtifactReference
from afre.health.evaluation import snapshot_for as health_snapshot_for
from afre.schema import Artifact, require
from afre.service.context import ContextField, ContextRequest, SnapshotContext
from afre.service.native import NativeSnapshotSource
from afre.service.schema import ServiceContextKind as K

if TYPE_CHECKING:
    from afre.service.repository import ServiceRepository

CONTEXT_TYPES = {
    K.RANKING: ("CrossSectionRanking",),
    K.EVENT: ("EventConditionedForecast", "EventReference"),
    K.REGIME: ("RegimeConditionedForecast", "RegimeSnapshot"),
    K.UNCERTAINTY: ("ForecastUncertaintyDecomposition",),
    K.ORTHOGONAL: ("OrthogonalSignalValue",),
    K.FUSION: ("FusedForecast",),
    K.HEALTH: ("ModelHealthSnapshot",),
    K.CHALLENGE: ("ChallengeRun",),
}
OMIT = {
    "target_id",
    "target_available_ns",
    "truth_ids",
    "rows",
    "response",
    "truth",
    "evidence_id",
    "common_id",
    "sample_truth_ids",
    "train_sample_ids",
}


def project(
    value: object, prefix: str = "", *, maximum: int = 4096
) -> tuple[ContextField, ...]:
    result: list[ContextField] = []

    def visit(item: object, path: str, depth: int) -> None:
        require(depth <= 32 and len(result) < maximum, "context field/depth bound")
        if isinstance(item, Artifact):
            for f in fields(item):
                if f.name not in OMIT:
                    visit(getattr(item, f.name), path + f.name + ".", depth + 1)
        elif isinstance(item, tuple):
            for i, child in enumerate(item):
                visit(child, path + str(i) + ".", depth + 1)
        elif isinstance(item, Enum):
            visit(item.value, path, depth + 1)
        else:
            require(
                item is None or type(item) in (str, int, float, bool),
                "context scalar projection",
            )
            result.append(
                ContextField(path.rstrip("."), cast(str | float | int | bool | None, item))
            )

    visit(value, prefix, 0)
    return tuple(result)


def context_for(
    repo: "ServiceRepository",
    request: ContextRequest,
    source: NativeSnapshotSource,
    published_ns: int,
) -> SnapshotContext:
    raw = repo.raw(request.artifact_id)
    require(type(raw).__name__ in CONTEXT_TYPES[request.kind], "INCOMPATIBLE: context type")
    extra: list[ContextField] = []
    available = getattr(raw, "available_ns", None)
    cutoff = getattr(raw, "cutoff_ns", None)
    target, horizon = source.target.fingerprint, source.target.horizon.fingerprint
    if isinstance(raw, ModelHealthSnapshot):
        ref = repo.get(MonitoredArtifactReference, raw.reference_id)
        require(
            (ref.target_id, ref.horizon_id, ref.producer_id)
            == (target, horizon, source.producer_id),
            "INCOMPATIBLE: health producer",
        )
        metrics = tuple(repo.get(HealthMetric, i) for i in raw.metric_ids)
        health_spec = repo.get(HealthSpec, raw.spec_id)
        require(
            raw == health_snapshot_for(health_spec, metrics, raw.available_ns),
            "health snapshot metadata corruption",
        )
        for i, identity in enumerate(raw.metric_ids):
            metric = repo.get(HealthMetric, identity)
            require(
                metric.spec_id == raw.spec_id
                and metric.available_ns <= raw.available_ns
                and metric.cutoff_ns == raw.cutoff_ns,
                "health metric metadata corruption",
            )
            extra.extend(
                (
                    ContextField(f"metrics.{i}.id", identity),
                    ContextField(f"metrics.{i}.kind", metric.kind.value),
                    ContextField(f"metrics.{i}.status", metric.status.value),
                )
            )
    elif isinstance(raw, ChallengeRun):
        program = repo.get(ChallengeProgram, raw.program_id)
        participants = tuple(
            repo.get(ParticipantReference, i)
            for i in (program.champion_id, *program.challenger_ids)
        )
        require(
            (program.target_id, program.horizon_id) == (target, horizon)
            and source.producer_id in {p.reference.producer_id for p in participants}
            and raw.champion_id == program.champion_id
            and raw.challenger_ids == program.challenger_ids,
            "INCOMPATIBLE: challenge participant/target",
        )
        extra.extend(project(program, "program.", maximum=repo.service_bounds.context_fields))
        for family, cls, identities in (
            ("promotion", PromotionAssessment, raw.promotion_ids),
            ("rollback", RollbackAssessment, raw.rollback_ids),
        ):
            for i, identity in enumerate(identities):
                assessment = repo.get(cls, identity)
                assert isinstance(assessment, (PromotionAssessment, RollbackAssessment))
                require(
                    getattr(assessment, "program_id", None) == raw.program_id,
                    "challenge assessment metadata corruption",
                )
                extra.extend(
                    (
                        ContextField(f"{family}.{i}.id", identity),
                        ContextField(f"{family}.{i}.status", assessment.outcome.value),
                    )
                )
    elif isinstance(raw, CrossSectionRanking):
        repo._validate_links(raw)
        spec = repo.get(CrossSectionSpec, raw.spec_id)
        require(
            spec.identity.snapshot_id == source.sample.snapshot_id
            and spec.identity.target == source.target,
            "INCOMPATIBLE: ranking universe/target",
        )
        entry = next((e for e in raw.entries if e.security == source.security), None)
        require(entry is not None, "INCOMPATIBLE: ranking security")
        assert entry is not None
        observation = repo.get(CrossSectionObservation, entry.observation_id)
        require(
            observation.origin == source.origin
            and observation.source_id == source.artifact.fingerprint,
            "INCOMPATIBLE: ranking source/origin",
        )
        extra.extend(project(spec, "definition."))
        extra.extend(project(entry, "entry."))
        extra.append(ContextField("entry.group_id", observation.group_id))
    else:
        repo._validate_links(raw)
        require(
            getattr(raw, "origin", source.origin) == source.origin,
            "INCOMPATIBLE: context origin",
        )
        require(
            getattr(raw, "sample_id", source.sample.fingerprint) == source.sample.fingerprint,
            "INCOMPATIBLE: context sample",
        )
        require(
            getattr(raw, "forecast_id", source.artifact.fingerprint)
            == source.artifact.fingerprint,
            "INCOMPATIBLE: uncertainty forecast",
        )
        require(
            getattr(raw, "target_definition_id", getattr(raw, "target_id", target)) == target,
            "INCOMPATIBLE: context target",
        )
        if request.kind in (K.EVENT, K.REGIME, K.FUSION):
            require(
                raw.fingerprint == source.artifact.fingerprint
                or raw.fingerprint in getattr(source.artifact, "event_ids", ())
                or raw.fingerprint == getattr(source.artifact, "regime_snapshot_id", None),
                "INCOMPATIBLE: context exact source reference",
            )
        if request.kind is K.REGIME:
            from afre.regime_conditioned.regimes import RegimeSnapshot
            from afre.regime_conditioned.schema import RegimeStateSemantics

            identity = getattr(raw, "regime_snapshot_id", raw.fingerprint)
            regime = repo.get(RegimeSnapshot, identity)
            require(
                regime.semantics is RegimeStateSemantics.FILTERED,
                "INCOMPATIBLE: noncausal regime",
            )
            extra.extend(project(regime, "regime."))
            available = max(available or 0, regime.clocks.final_available_ns)
        if request.kind is K.ORTHOGONAL:
            projection = repo.raw(getattr(raw, "projection_id", "missing"))
            orth_spec = repo.raw(getattr(projection, "spec_id", "missing"))
            require(
                getattr(orth_spec, "target", None) == source.target,
                "INCOMPATIBLE: orthogonal target/horizon",
            )
            extra.extend(project(projection, "projection."))
            extra.extend(project(orth_spec, "orthogonal_definition."))
        if request.kind is K.FUSION:
            model = repo.raw(getattr(raw, "artifact_id", "missing"))
            extra.extend(project(model, "fusion_model."))
            fusion_spec = repo.raw(getattr(model, "spec_id", "missing"))
            extra.extend(project(fusion_spec, "fusion_definition."))
        if request.kind is K.EVENT:
            spec_id = getattr(raw, "spec_id", None)
            if spec_id:
                extra.extend(project(repo.raw(spec_id), "event_definition."))
            for i, identity in enumerate(getattr(raw, "event_ids", ())):
                extra.extend(project(repo.raw(identity), f"events.{i}."))
            require(
                len(getattr(raw, "event_ids", ())) <= repo.service_bounds.event_refs,
                "event reference bound",
            )
        clocks = getattr(raw, "clocks", None)
        if clocks:
            available = clocks.final_available_ns
    require(type(available) is int, "context availability evidence required")
    assert isinstance(available, int)
    require(
        available
        <= (
            published_ns
            if request.historical_evaluation
            else source.origin.availability_cutoff_ns
        ),
        "INCOMPATIBLE: late context metadata",
    )
    projected = (*project(raw, maximum=repo.service_bounds.context_fields), *extra)
    require(len(projected) <= repo.service_bounds.context_fields, "context field bound")
    return SnapshotContext(
        request.kind,
        raw.fingerprint,
        projected,
        available,
        cutoff,
        request.historical_evaluation,
        "NONE_DESCRIPTIVE_ONLY"
        if request.kind is K.HEALTH
        else "MANUAL_ONLY"
        if request.kind is K.CHALLENGE
        else "RESEARCH_ONLY",
    )
