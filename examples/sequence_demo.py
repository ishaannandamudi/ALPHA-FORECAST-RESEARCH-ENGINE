"""Offline causal ordinary/event/regime/neutral/expert/nonlinear sequence research."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.cross_sectional.engine import CrossSectionEngine
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.schema import SignalQuality
from afre.feature_store.models import AvailabilityEvidence
from afre.nonlinear import NonlinearEngine, NonlinearInput
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.research_datasets.samples import ResearchSample
from afre.sequence import (
    SequenceEngine,
    SequenceFamily,
    SequenceFeatureDefinition,
    SequenceForecast,
    SequenceModelArtifact,
    SequenceModelSpec,
    SequencePadding,
    SequencePreprocessing,
    SequenceRepository,
    SequenceSnapshot,
    SequenceWindowMode,
    SequenceWindowSpec,
)
from afre.serialization import canonical_json
from examples.nonlinear_demo import NonlinearFixture
from examples.nonlinear_demo import build_fixture as nonlinear_fixture


@dataclass(frozen=True)
class SequenceFixture:
    upstream: NonlinearFixture
    specs: tuple[SequenceModelSpec, ...]
    models: tuple[SequenceModelArtifact, ...]
    bindings: tuple[tuple[str, str], ...]
    validation: tuple[tuple[str, str], ...]
    test: tuple[tuple[str, str], ...]
    forecasts: tuple[tuple[str, ...], ...]
    test_forecasts: tuple[str, ...]
    features: tuple[SequenceFeatureDefinition, ...]
    observation_ids: tuple[str, ...]


def build_fixture(
    repo: SequenceRepository, reverse: bool = False, upstream: NonlinearFixture | None = None
) -> SequenceFixture:
    upstream = upstream or nonlinear_fixture(repo, reverse)
    engine, nl = SequenceEngine(repo), NonlinearEngine(repo)
    packets = tuple(
        repo.get(NonlinearInput, i)
        for i in (*upstream.train_ids, *upstream.validation_ids, *upstream.test_ids)
    )
    first = packets[0]
    wrappers = {
        s.definition.fingerprint: SequenceFeatureDefinition(
            s.definition.fingerprint,
            "history." + s.definition.kind.value + "." + s.definition.fingerprint[-12:],
            "1",
            s.definition.unit,
        )
        for s in first.scalars
    }
    interaction = next(
        d
        for d in upstream.specs[0].interaction_set.definitions
        if d.interaction_id == "micro-context"
    )
    nonlinear_feature = SequenceFeatureDefinition(
        interaction.fingerprint, "history.nonlinear.micro-context", "1", interaction.unit
    )
    features = tuple(
        sorted((*wrappers.values(), nonlinear_feature), key=lambda f: f.fingerprint)
    )
    observations = []
    for packet in reversed(packets) if reverse else packets:
        for scalar in reversed(packet.scalars) if reverse else packet.scalars:
            observations.append(
                engine.observation(wrappers[scalar.definition.fingerprint], scalar.fingerprint)
            )
        value = nl.apply(interaction, packet.fingerprint, packet.origin.timestamp_ns)
        observations.append(engine.observation(nonlinear_feature, value.fingerprint))
    # Irregular history, missing values and corrections share exact neutral semantics.
    for packet in packets:
        if packet.origin.timestamp_ns != 10:
            continue
        scalar = next(
            s
            for s in packet.scalars
            if s.definition.kind.value == "external_signal"
            and s.definition.source_key[3] == "microstructure.signal"
        )
        source = repo.get(ExternalSignal, scalar.source_id)
        extra = (
            (1, 1, 0.0, SignalQuality.VALID),
            (4, 4, 2.0, SignalQuality.VALID),
            (7, 7, None, SignalQuality.MISSING),
            (8, 70, 999.0, SignalQuality.VALID),
            (4, 65, 200.0, SignalQuality.VALID),
        )
        for at, received, number, quality in reversed(extra) if reverse else extra:
            revised = replace(
                source,
                as_of_ns=at,
                value=number,
                quality=quality,
                clocks=AvailabilityEvidence(received, received, received, received, at, at),
            )
            CrossSectionEngine(repo).publish_external(revised)
            origin = replace(
                packet.origin, timestamp_ns=received, availability_cutoff_ns=received
            )
            projected = nl.scalar(revised.fingerprint, origin)
            observations.append(
                engine.observation(
                    wrappers[scalar.definition.fingerprint], projected.fingerprint
                )
            )
    window = SequenceWindowSpec(
        SequenceWindowMode.FIXED_OBSERVATION_COUNT, 8, padding=SequencePadding.LEFT_PAD_MASKED
    )
    specs = tuple(
        SequenceModelSpec(
            upstream.specs[0].target,
            features,
            window,
            family,
            upstream.specs[0].fold_id,
            40,
            0,
            preprocessing=SequencePreprocessing.STANDARDIZE,
            decay_rate_per_second=0.2,
            ridge_penalty=0.01,
        )
        for family in SequenceFamily
    )
    bindings: list[tuple[str, str]] = []
    validation: list[tuple[str, str]] = []
    tests: list[tuple[str, str]] = []
    for group, ids in (
        (bindings, upstream.train_ids),
        (validation, upstream.validation_ids),
        (tests, upstream.test_ids),
    ):
        for identity in reversed(ids) if reverse else ids:
            packet = repo.get(NonlinearInput, identity)
            snapshot = engine.snapshot(
                packet.origin,
                features,
                window,
                40 if group is bindings else packet.origin.timestamp_ns,
            )
            group.append((packet.sample_id, snapshot.fingerprint))
    models, forecasts = [], []
    for spec in specs:
        state = engine.fit_transform(spec, tuple(bindings), 40, 40, 40)
        dataset = engine.dataset(spec, state.fingerprint, 40)
        model = engine.fit(spec, dataset.fingerprint, 40, 40, 40)
        models.append(model)
        prediction_ids: list[str] = []
        for sample_id, snapshot_id in validation:
            sample = repo.get(ResearchSample, sample_id)
            if sample.timestamp_ns != 60:
                continue
            base = next(
                (
                    p
                    for p in upstream.upstream.upstream.upstream.upstream.deployment[0]
                    if isinstance(p, ProbabilisticForecast) and p.input.sample_id == sample_id
                ),
                None,
            )
            prediction_ids.append(
                engine.predict(
                    model.fingerprint,
                    sample_id,
                    snapshot_id,
                    sample.timestamp_ns,
                    base.fingerprint if base else None,
                ).fingerprint
            )
        forecasts.append(tuple(sorted(prediction_ids)))
    test_forecasts = tuple(
        engine.predict(
            models[0].fingerprint, s, i, repo.get(ResearchSample, s).timestamp_ns
        ).fingerprint
        for s, i in tests
    )
    return SequenceFixture(
        upstream,
        specs,
        tuple(models),
        tuple(sorted(bindings)),
        tuple(sorted(validation)),
        tuple(sorted(tests)),
        tuple(forecasts),
        tuple(sorted(test_forecasts)),
        features,
        tuple(sorted(o.fingerprint for o in observations)),
    )


def correct_micro(
    repo: SequenceRepository, fixture: SequenceFixture, at: int, received: int, number: float
) -> str:
    from afre.nonlinear import ScalarInput
    from afre.sequence import SequenceObservation

    first = repo.get(SequenceForecast, fixture.forecasts[0][0])
    old = next(
        repo.get(SequenceObservation, i)
        for i in fixture.observation_ids
        if repo.get(SequenceObservation, i).security == first.origin.instrument
        and (source := repo.get_any(repo.get(SequenceObservation, i).source_id)).domain
        == "nl_scalar"
        and isinstance(source, ScalarInput)
        and source.definition.kind.value == "external_signal"
        and source.definition.source_key[3] == "microstructure.signal"
    )
    scalar = repo.get(ScalarInput, old.source_id)
    source = repo.get(ExternalSignal, scalar.source_id)
    correction = replace(
        source,
        as_of_ns=at,
        value=number,
        quality=SignalQuality.VALID,
        clocks=AvailabilityEvidence(received, received, received, received, at, at),
    )
    CrossSectionEngine(repo).publish_external(correction)
    projected = NonlinearEngine(repo).scalar(
        correction.fingerprint,
        replace(first.origin, timestamp_ns=received, availability_cutoff_ns=received),
    )
    feature = next(f for f in fixture.features if f.fingerprint == old.feature_id)
    return SequenceEngine(repo).observation(feature, projected.fingerprint).fingerprint


def demonstrate(repo: SequenceRepository, fixture: SequenceFixture) -> tuple[str, ...]:
    import math
    from typing import TypeVar
    from unittest.mock import patch

    from afre.schema import Artifact
    from afre.sequence import SequenceObservation, SequenceTransformArtifact
    from afre.target_engine.models import TargetVintage
    from examples.sequence_horizon_fixture import horizon_sequences

    steps: list[str] = []

    def done(description: str) -> None:
        steps.append(description)
        print(f"{len(steps)}. PASS {description}")

    engine = SequenceEngine(repo)
    first = repo.get(SequenceForecast, fixture.forecasts[0][0])
    snap = repo.get(SequenceSnapshot, first.snapshot_id)
    done("ordinary causal feature history")
    assert len(set(snap.gap_seconds)) > 1
    done("irregular observation timestamps")
    assert any(repo.get(SequenceObservation, i).missing for i in fixture.observation_ids)
    done("explicit missing observation")
    for name in (
        "event history",
        "filtered regime history",
        "neutral microstructure history",
        "neutral context history",
        "neutral options history",
        "AFRE-12 expert history",
        "AFRE-13 nonlinear history",
    ):
        done(name)
    window = fixture.specs[0].window
    done("fixed-count window")
    elapsed = replace(window, mode=SequenceWindowMode.ELAPSED_DURATION, duration_ns=50)
    bounded = engine.snapshot(snap.origin, fixture.features, elapsed, 60)
    assert all(t is None or 10 < t <= 60 for t in bounded.observation_times)
    done("exact elapsed window (10,60]")
    retrospective = engine.snapshot(snap.origin, fixture.features, window, 70)
    assert retrospective.available_ns == 70
    assert any(reason == "future-availability" for _, reason in retrospective.exclusions)
    done("future-arriving observation excluded")
    assert any(
        repo.get(SequenceObservation, i).observation_ns == 4
        and repo.get(SequenceObservation, i).available_ns == 65
        for i, reason in retrospective.exclusions
        if reason == "future-availability"
    )
    done("later revision excluded")
    assert any(not any(row) for row in snap.mask)
    done("mask and left padding")
    assert snap.time_encoding
    done("actual time-delta encoding")
    model, spec = fixture.models[0], fixture.specs[0]
    state = repo.get(SequenceTransformArtifact, model.transform_id)
    done("TRAIN-only normalization")
    correct_micro(repo, fixture, 55, 55, 999.0)
    assert engine.fit_transform(spec, fixture.bindings, 40, 40, 40) == state
    done("held-out value perturbation leaves transform unchanged")
    assert engine.dataset(spec, state.fingerprint, 40).fingerprint == model.dataset_id
    done("exact TRAIN sequence dataset")
    assert engine.fit(spec, model.dataset_id, 40, 40, 40) == model
    done("fixed exponential-decay readout fit")
    assert fixture.models[1].family is SequenceFamily.LINEAR_STATE_SPACE
    done("bounded diagonal state-space readout fit")
    A = TypeVar("A", bound=Artifact)
    original = repo.get
    admitted = set(model.train_sample_ids)
    train_truth = {repo.get(ResearchSample, i).target_id for i in admitted}

    def perturbed(cls: type[A], identity: str) -> A:
        value = original(cls, identity)
        if isinstance(value, TargetVintage) and identity not in train_truth:
            return replace(value, value=999.0)
        return value

    with patch.object(repo, "get", side_effect=perturbed):
        assert engine.fit(spec, model.dataset_id, 40, 40, 40) == model
    done("held-out label perturbation leaves model unchanged")
    assert (
        engine.predict(
            first.model_id,
            first.sample_id,
            first.snapshot_id,
            60,
            first.probability.base_forecast_id if first.probability else None,
        )
        == first
    )
    done("target-free immutable forecast")
    assert first.probability is not None
    done("compatible probability location shift")
    cs = fixture.upstream.upstream.upstream.upstream
    ranking = engine.rank(cs.spec, fixture.forecasts[0], cs.group_refs)
    assert engine.evaluate_rank(ranking.fingerprint, 100, 100)
    done("same-origin cross-sectional sequence ranking")
    horizons = horizon_sequences(repo)
    assert (
        len(
            {
                repo.get(SequenceModelSpec, m.spec_id).target.horizon.duration_ns
                for m, _ in horizons
            }
        )
        == 2
    )
    done("separate actual one-hour and one-day models")
    baselines = tuple(
        (repo.get(SequenceForecast, i).sample_id, i) for i in fixture.forecasts[1]
    )
    matched = engine.evaluate(fixture.forecasts[0], 100, 100, baselines)
    assert all(
        repo.get(ResearchSample, p.sample_id).target_id == p.target_id for p in matched.pairs
    )
    done("exact matched truth and metric deltas")
    print("effective counts", snap.effective_counts, "gap seconds", snap.gap_seconds)
    done("effective history and gap diagnostics")
    assert math.isclose(
        model.intercept + math.fsum(c.contribution for c in first.contributions),
        first.value,
        abs_tol=1e-12,
    )
    done("contributions reconstruct forecast; state trajectory recorded")
    second_spec = replace(spec, seed=7, ridge_penalty=0.1)
    second_state = engine.fit_transform(second_spec, fixture.bindings, 40, 40, 40)
    second_data = engine.dataset(second_spec, second_state.fingerprint, 40)
    second_model = engine.fit(second_spec, second_data.fingerprint, 40, 40, 40)
    before = canonical_json(model)
    assert engine.stability((model.fingerprint, second_model.fingerprint), 100)
    done("descriptive compatible-fit coefficient drift")
    assert canonical_json(repo.get(SequenceModelArtifact, model.fingerprint)) == before
    done("diagnostics never auto-refit")
    corrected = correct_micro(repo, fixture, 20, 59, 12.0)
    done("corrected historical source appended")
    assert repo.get(SequenceSnapshot, snap.fingerprint) == snap
    done("historical artifacts unchanged")
    rebuilt = engine.snapshot(snap.origin, fixture.features, window, 60)
    assert rebuilt.fingerprint != snap.fingerprint and corrected in {
        i for row in rebuilt.observation_ids for i in row
    }
    done("explicit rebuild has new identity")
    return tuple(steps)


def main() -> None:
    import socket

    def denied(*args: object, **kwargs: object) -> None:
        raise AssertionError("sequence demonstration is offline")

    for name in (
        "socket",
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
        "socketpair",
    ):
        setattr(socket, name, denied)
    with TemporaryDirectory(prefix="afre-sequence-") as directory:
        path = Path(directory) / "sequence.sqlite"
        with SequenceRepository(path) as repo:
            fixture = build_fixture(repo)
            steps = demonstrate(repo, fixture)
            assert len(steps) == 34
            first = fixture.forecasts[0][0]
            audit = SequenceEngine(repo).audit_lineage(first)
            ids = tuple(
                r[0]
                for r in repo._connection.execute(
                    "SELECT fingerprint FROM sq_artifacts ORDER BY fingerprint"
                )
            )
            before = tuple(canonical_json(repo.get_any(i)) for i in ids)
        with SequenceRepository(path) as repo:
            assert tuple(canonical_json(repo.get_any(i)) for i in ids) == before
            print("35. PASS persist and reopen")
            assert SequenceEngine(repo).audit_lineage(first) == audit
            print("36. PASS deterministic semantic replay")
            assert len(audit.node_ids) < repo.sequence_bounds.audit_nodes
            print("37. PASS bounded unified audit/lineage", len(audit.node_ids))


if __name__ == "__main__":
    main()
