"""Offline neutral events, interpretable effects, independent clocks and matched diagnostics."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.cross_sectional import CrossSectionEngine, CrossSectionEvaluation, GroupMembership
from afre.event_conditioned import (
    EventClass,
    EventConditionedForecast,
    EventConditionedModel,
    EventConditioningSpec,
    EventEngine,
    EventModelFamily,
    EventOverlapPolicy,
    EventReference,
    EventRelation,
    EventRepository,
    EventScope,
    EventSubject,
    EventSurprise,
    EventValue,
    EventValueRule,
    EventWindowSpec,
)
from afre.event_conditioned.artifacts import (
    EventConditionedEvaluation,
    EventConditionedObservation,
    EventMatchSet,
)
from afre.event_conditioned.fitting import feature_keys
from afre.research_datasets.samples import ResearchSample
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import DesignMatrix, FittedModelArtifact, ModelFitInputs
from examples.cross_sectional_demo import (
    CrossSectionFixture,
    cross_fixture,
    external,
    provider_source,
)
from examples.feature_store_demo import clocks


def value(
    number: float, at: int, unit: str = "fraction", method: str = "fixed-input"
) -> EventValue:
    return EventValue(
        number,
        unit,
        method,
        "1",
        "synthetic-event-provider",
        at,
        clocks(at),
        provider_source("synthetic-event-provider"),
        0.0 if unit == "fraction" else None,
        1.0 if unit == "fraction" else None,
    )


def event(
    sample: ResearchSample,
    name: str,
    at: int | None = None,
    received: int | None = None,
    score: float | None = None,
    subject: EventSubject | None = None,
    revision: str = "1",
) -> EventReference:
    at = sample.timestamp_ns if at is None else at
    received = at if received is None else received
    score = 0.1 + 0.15 * int(sample.security.value) + 0.001 * at if score is None else score
    actual, expected = value(score, at, "unit", "actual"), value(0.0, at, "unit", "expectation")
    return EventReference(
        name,
        revision,
        "1.0",
        "synthetic-event-provider",
        "1",
        EventClass.EARNINGS if int(sample.security.value) < 2 else EventClass.GUIDANCE,
        "scheduled-result",
        (),
        subject or EventSubject(EventScope.SECURITY, security=sample.security),
        at,
        replace(clocks(received), upstream_publication_ns=at, upstream_available_ns=at),
        provider_source("synthetic-event-provider"),
        materiality=value(score, at),
        novelty=value(score, at),
        surprise=EventSurprise(actual, expected, 1.0, "actual-minus-expectation-v1", at, at),
    )


@dataclass(frozen=True)
class EventFixture:
    upstream: CrossSectionFixture
    spec: EventConditioningSpec
    model: EventConditionedModel
    training_observation_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    forecast_ids: tuple[str, ...]


def build_fixture(
    repo: EventRepository,
    reverse: bool = False,
    upstream: CrossSectionFixture | None = None,
    horizon_index: int = 0,
) -> EventFixture:
    upstream = upstream or cross_fixture(repo, reverse)
    binding = upstream.upstream.spec.bindings[horizon_index]
    engine = EventEngine(repo)
    base = repo.get(FittedModelArtifact, binding.point_model_id)
    inputs = repo.get(ModelFitInputs, base.fit_inputs_id)
    matrix = repo.get(DesignMatrix, inputs.matrix_id)
    spec = EventConditioningSpec(
        binding.point_model_id,
        EventWindowSpec(
            upstream.upstream.spec.horizon_set.targets[horizon_index], EventRelation.AT_EVENT
        ),
        tuple(EventClass),
        tuple(EventScope),
    )
    observations: list[EventConditionedObservation] = []
    events: list[str] = []
    rows = tuple(reversed(matrix.rows)) if reverse else matrix.rows
    for row in rows:
        sample = repo.get(ResearchSample, row.sample_id)
        e = event(sample, "train:" + sample.fingerprint)
        identity = engine.publish_event(e)
        events.append(identity)
        observations.extend(engine.observe(spec, sample.fingerprint, (identity,)))
    model = engine.fit(spec, tuple(o.fingerprint for o in observations), 40, 40, 40)
    forecasts = []
    deployed = (
        tuple(reversed(upstream.upstream.deployment[horizon_index]))
        if reverse
        else upstream.upstream.deployment[horizon_index]
    )
    for raw in deployed:
        sample = repo.get(ResearchSample, raw.input.sample_id or "")
        e = event(
            sample,
            "deployment:" + sample.security.fingerprint,
            received=61 if sample.security.value == "0004" else 60,
        )
        identity = engine.publish_event(e)
        events.append(identity)
        observation = engine.observe(spec, sample.fingerprint, (identity,))[0]
        forecasts.append(
            engine.forecast(
                model.fingerprint,
                observation.fingerprint,
                raw.point_forecast_id,
                60,
                raw.fingerprint,
            ).fingerprint
        )
    return EventFixture(
        upstream,
        spec,
        model,
        tuple(sorted(o.fingerprint for o in observations)),
        tuple(sorted(events)),
        tuple(sorted(forecasts)),
    )


def main() -> None:
    with TemporaryDirectory() as folder:
        path = Path(folder) / "event-conditioned.sqlite"
        with EventRepository(path) as repo:
            f = build_fixture(repo)
            engine = EventEngine(repo)
            forecasts = tuple(repo.get(EventConditionedForecast, i) for i in f.forecast_ids)
            base_bytes = tuple(
                canonical_json(repo.get_any(p.base_forecast_id)) for p in forecasts
            )
            evaluation = engine.evaluate(f.forecast_ids, 100, 100)
            rank = engine.rank(f.upstream.spec, f.forecast_ids, f.upstream.group_refs)
            rank_eval = engine.evaluate_rank(rank.fingerprint, 100, 100)
            cs = repo.get(CrossSectionEvaluation, rank_eval.cross_section_evaluation_id)
            affected = next(p for p in forecasts if p.event_ids)
            sample = repo.get(
                ResearchSample,
                repo.get(EventConditionedObservation, affected.observation_id).sample_id,
            )
            second = engine.publish_event(
                event(sample, "simultaneous", subject=EventSubject(EventScope.MACRO))
            )
            separate = replace(f.spec, overlap=EventOverlapPolicy.ALL_EVENTS_SEPARATE)
            original = affected.event_ids[0]
            overlap = engine.observe(
                separate, sample.fingerprint, tuple(set((original, second)))
            )
            assert overlap
            selected = repo.get(EventMatchSet, overlap[0].matches_id)
            assert len(selected.selected_ids) == 2
            nearest = engine.observe(
                replace(separate, overlap=EventOverlapPolicy.NEAREST_EVENT),
                sample.fingerprint,
                (original, second),
            )
            assert len(nearest) == 1
            membership_id = next(
                i for s, i in f.upstream.group_refs if s == sample.security.fingerprint
            )
            membership = repo.get(GroupMembership, membership_id)
            assert f.upstream.spec.group is not None
            sector = engine.publish_event(
                event(
                    sample,
                    "sector-event",
                    subject=EventSubject(
                        EventScope.SECTOR,
                        group_policy=f.upstream.spec.group,
                        group_id=membership.group_id,
                    ),
                )
            )
            assert engine.observe(
                f.spec, sample.fingerprint, (sector,), mapping_ids=(membership_id,)
            )[0].event_id
            linear = tuple(
                build_linear_fixture(repo, f, key, family)
                for key, family in (
                    ("materiality", EventModelFamily.MATERIALITY_LINEAR),
                    ("surprise", EventModelFamily.SURPRISE_LINEAR),
                )
            )
            # The independent reaction clock cannot be inferred from event availability.
            reaction = external(sample.security, 60, 0.1, 61)
            CrossSectionEngine(repo).publish_external(reaction)
            reaction_spec = replace(
                f.spec,
                family=EventModelFamily.EVENT_FEATURE_LINEAR,
                window=replace(
                    f.spec.window, relation=EventRelation.POST_EVENT, post_maximum_age_ns=2
                ),
                reaction_specs=(f.upstream.spec.score,),
            )
            reaction_event = engine.publish_event(event(sample, "reaction-origin", at=59))
            late_reaction = engine.observe(
                reaction_spec, sample.fingerprint, (reaction_event,), (reaction.fingerprint,)
            )[0]
            assert not late_reaction.event_id
            live = external(sample.security, 60, 0.1, 60)
            CrossSectionEngine(repo).publish_external(live)
            assert engine.observe(
                reaction_spec, sample.fingerprint, (reaction_event,), (live.fingerprint,)
            )[0].reaction_ids == (live.fingerprint,)
            other_horizon = build_fixture(repo, upstream=f.upstream, horizon_index=1)
            other_evaluation = engine.evaluate(other_horizon.forecast_ids, 100, 100)
            assert (
                other_horizon.model != f.model
                and other_evaluation.model_id != evaluation.model_id
            )
            old = canonical_json(affected)
            corrected = engine.publish_event(
                replace(repo.get(EventReference, original), revision="corrected")
            )
            corrected_obs = engine.observe(f.spec, sample.fingerprint, (corrected,))[0]
            changed = engine.forecast(
                f.model.fingerprint,
                corrected_obs.fingerprint,
                affected.base_forecast_id,
                60,
                affected.base_probability_id,
            )
            assert changed.fingerprint != affected.fingerprint
            assert (
                canonical_json(repo.get(EventConditionedForecast, affected.fingerprint)) == old
            )
            audit = engine.audit_lineage(rank_eval.fingerprint)
            assert base_bytes == tuple(
                canonical_json(repo.get_any(p.base_forecast_id)) for p in forecasts
            )
            repo.audit()
            print(
                {
                    "forecasts": len(forecasts),
                    "affected": evaluation.affected_count,
                    "matched_truths": len(evaluation.pairs),
                    "event_IC": cs.pearson.value,
                    "overlap_relations": len(selected.selected_ids),
                    "linear_models": tuple(m.model.coefficients for m in linear),
                    "horizons": (
                        f.spec.window.target.horizon.fingerprint,
                        other_horizon.spec.window.target.horizon.fingerprint,
                    ),
                    "audit_nodes": len(audit.evidence_ids),
                    "feature_keys": feature_keys(f.spec),
                }
            )
        with EventRepository(path) as repo:
            assert (
                canonical_json(repo.get(EventConditionedForecast, affected.fingerprint)) == old
            )
            assert repo.get(EventConditionedEvaluation, evaluation.fingerprint) == evaluation
            repo.audit()


def build_linear_fixture(
    repo: EventRepository, source: EventFixture, key: str, family: EventModelFamily
) -> EventFixture:
    """Independent TRAIN-only one-feature regression with exact source semantics."""
    engine = EventEngine(repo)
    original = repo.get(EventConditionedObservation, source.training_observation_ids[0])
    example = repo.get(EventReference, original.event_id or "")
    attribute = getattr(example, key)
    assert isinstance(attribute, (EventValue, EventSurprise))
    spec = replace(
        source.spec,
        family=family,
        value_rules=(
            EventValueRule(
                key,
                attribute.semantic_key,
                use_as_feature=True,
            ),
        ),
    )
    observations = tuple(
        engine.observe(spec, o.sample_id, (o.event_id or "",))[0]
        for o in (
            repo.get(EventConditionedObservation, i) for i in source.training_observation_ids
        )
    )
    model = engine.fit(spec, tuple(o.fingerprint for o in observations), 40, 40, 40)
    forecasts = []
    for identity in source.forecast_ids:
        prior = repo.get(EventConditionedForecast, identity)
        o = repo.get(EventConditionedObservation, prior.observation_id)
        candidates = repo.get(EventMatchSet, o.matches_id).event_ids
        observed = engine.observe(spec, o.sample_id, candidates)[0]
        forecasts.append(
            engine.forecast(
                model.fingerprint,
                observed.fingerprint,
                prior.base_forecast_id,
                60,
                prior.base_probability_id,
            ).fingerprint
        )
    return EventFixture(
        source.upstream,
        spec,
        model,
        tuple(sorted(o.fingerprint for o in observations)),
        source.event_ids,
        tuple(sorted(forecasts)),
    )


if __name__ == "__main__":
    main()
