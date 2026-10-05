"""Deterministic neutral specialist inputs; external forecasts never read truth."""

from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from afre.event_conditioned.artifacts import EventConditionedForecast
from afre.mixture import (
    ExpertKind,
    ExpertMissingPolicy,
    ExpertOutput,
    ExpertQuality,
    ExpertReference,
    ExpertSet,
    ExternalExpertForecast,
    FixedGateSpec,
    GateModelArtifact,
    LearnedGateSpec,
    MixtureEngine,
    MixtureForecast,
    MixtureRepository,
    MixtureRequest,
)
from afre.probabilistic.artifacts import DistributionParameters
from afre.probabilistic.definitions import ThresholdRequest
from afre.probabilistic.schema import DistributionFamily, ThresholdComparison
from afre.regime_conditioned.artifacts import RegimeConditionedForecast
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact
from afre.statistical_models.definitions import BaselineModelSpec
from afre.target_engine.definitions import TargetDefinition
from examples.cross_sectional_demo import provider_source
from examples.event_conditioned_demo import build_fixture as event_fixture
from examples.feature_store_demo import clocks
from examples.regime_conditioned_demo import RegimeFixture
from examples.regime_conditioned_demo import build_fixture as regime_fixture


def external_reference(
    target: TargetDefinition,
    kind: ExpertKind,
    label: str,
    output: ExpertOutput = ExpertOutput.POINT,
) -> ExpertReference:
    source = provider_source("synthetic-" + label)
    return ExpertReference(
        label,
        kind,
        source.provenance.system,
        source.provenance.source_version,
        "1.0",
        target,
        source.fingerprint,
        output,
        0,
        source,
    )


def external_binding(
    repo: MixtureRepository,
    expert: ExpertReference,
    sample: ResearchSample,
    point: float | None = None,
    distribution: DistributionParameters | None = None,
    received: int | None = None,
    revision: str = "1",
) -> str:
    assert sample.origin is not None
    at = sample.timestamp_ns
    delivery = clocks(at if received is None else received)
    delivery = replace(delivery, upstream_publication_ns=at, upstream_available_ns=at)
    forecast = ExternalExpertForecast(
        expert,
        sample.origin,
        at,
        delivery,
        expert.source,
        ExpertQuality.VALID,
        point,
        distribution,
        revision,
    )
    engine = MixtureEngine(repo)
    return engine.bind(expert.fingerprint, engine.publish_external(forecast)).fingerprint


def fixed_gate(
    repo: MixtureRepository,
    experts: tuple[ExpertReference, ...],
    missing: ExpertMissingPolicy = ExpertMissingPolicy.FAIL,
    fallback: str | None = None,
) -> FixedGateSpec:
    spec = ExpertSet(experts, experts[0].target, missing, fallback)
    gate = FixedGateSpec(spec, tuple((e.fingerprint, 1 / len(experts)) for e in spec.experts))
    MixtureEngine(repo).publish_gate(gate)
    return gate


@dataclass(frozen=True)
class MixtureFixture:
    upstream: RegimeFixture
    fold_id: str
    fixed: FixedGateSpec
    learned_spec: LearnedGateSpec
    learned: GateModelArtifact
    probability: FixedGateSpec
    training_ids: tuple[str, ...]
    forecast_ids: tuple[str, ...]
    test_ids: tuple[str, ...]
    learned_ids: tuple[str, ...]
    probability_ids: tuple[str, ...]


def build_fixture(repo: MixtureRepository, reverse: bool = False) -> MixtureFixture:
    upstream = regime_fixture(repo, reverse=reverse)
    events = event_fixture(repo, reverse=reverse, upstream=upstream.upstream)
    target = upstream.spec.target
    native_model = repo.get(FittedModelArtifact, upstream.spec.base_model_id)
    fold_id = repo.get(BaselineModelSpec, native_model.spec_id).fold_id
    source = provider_source("AFRE")
    native = tuple(
        ExpertReference(
            name,
            kind,
            "AFRE",
            source.provenance.source_version,
            "1.0",
            target,
            model.fingerprint,
            ExpertOutput.POINT,
            model.available_ns,
            source,
        )
        for name, kind, model in (
            ("statistical", ExpertKind.AFRE_POINT, native_model),
            ("event", ExpertKind.AFRE_EVENT, events.model),
            ("regime", ExpertKind.AFRE_REGIME, upstream.model),
        )
    )
    micro = external_reference(target, ExpertKind.EXTERNAL_MICROSTRUCTURE, "microstructure")
    context = external_reference(target, ExpertKind.EXTERNAL_CONTEXT, "context")
    options = external_reference(target, ExpertKind.EXTERNAL_OPTIONS, "options")
    all_experts = (*native, micro, context, options)
    fixed = fixed_gate(repo, tuple(reversed(all_experts)) if reverse else all_experts)
    engine = MixtureEngine(repo)
    train_set = ExpertSet((context, micro), target)
    learned_spec = LearnedGateSpec(train_set, fold_id, 40)
    engine.publish_gate(learned_spec)
    train = repo.partition_samples(fold_id, Partition.TRAIN)
    rows = []
    for sample in tuple(reversed(train)) if reverse else train:
        inputs = (
            external_binding(repo, micro, sample, 0.0),
            external_binding(repo, context, sample, 0.01),
        )
        row = engine.training_row(
            learned_spec, sample.fingerprint, tuple(reversed(inputs)) if reverse else inputs
        )
        rows.append(row.fingerprint)
    learned = engine.fit(learned_spec, tuple(rows), 40, 40, 40)
    probability_native = upstream.upstream.upstream.deployment[0][0]
    probability_model = repo.get_any(probability_native.model_artifact_id)
    native_probability = ExpertReference(
        "statistical-probability",
        ExpertKind.AFRE_PROBABILISTIC,
        "AFRE",
        source.provenance.source_version,
        "1.0",
        target,
        probability_model.fingerprint,
        ExpertOutput.PROBABILISTIC,
        probability_native.model_available_ns,
        source,
    )
    gaussian = external_reference(
        target,
        ExpertKind.EXTERNAL_MICROSTRUCTURE,
        "gaussian-specialist",
        ExpertOutput.PROBABILISTIC,
    )
    empirical = external_reference(
        target, ExpertKind.EXTERNAL_CONTEXT, "empirical-specialist", ExpertOutput.PROBABILISTIC
    )
    probability = fixed_gate(repo, (native_probability, gaussian, empirical))
    outputs, learned_outputs, probability_outputs = [], [], []
    for raws in (upstream.upstream.upstream.deployment[0], upstream.upstream.upstream.tests[0]):
        point_outputs = []
        for raw in tuple(reversed(raws)) if reverse else raws:
            sample = repo.get(ResearchSample, raw.input.sample_id or "")
            assert sample.origin is not None
            event_ids = events.forecast_ids if sample.timestamp_ns == 60 else ()
            event_forecast = next(
                (
                    repo.get(EventConditionedForecast, i)
                    for i in event_ids
                    if repo.get(EventConditionedForecast, i).origin == sample.origin
                ),
                None,
            )
            if event_forecast is None:
                from afre.event_conditioned import EventEngine
                from examples.event_conditioned_demo import event

                ee = EventEngine(repo)
                occurrence = ee.publish_event(
                    event(sample, "mixture-test-event:" + sample.fingerprint)
                )
                observation = ee.observe(events.spec, sample.fingerprint, (occurrence,))[0]
                event_forecast = ee.forecast(
                    events.model.fingerprint,
                    observation.fingerprint,
                    raw.point_forecast_id,
                    sample.timestamp_ns,
                    raw.fingerprint,
                )
            regimes = upstream.forecast_ids if sample.timestamp_ns == 60 else upstream.test_ids
            regime = next(
                repo.get(RegimeConditionedForecast, i)
                for i in regimes
                if repo.get(RegimeConditionedForecast, i).origin == sample.origin
            )
            ext_inputs = {
                micro.fingerprint: external_binding(repo, micro, sample, 0.0),
                context.fingerprint: external_binding(repo, context, sample, 0.01),
                options.fingerprint: external_binding(repo, options, sample, 0.002),
            }
            native_inputs = {
                e.fingerprint: engine.bind(e.fingerprint, identity).fingerprint
                for e, identity in zip(
                    native,
                    (raw.point_forecast_id, event_forecast.fingerprint, regime.fingerprint),
                    strict=True,
                )
            }
            grid = tuple({**ext_inputs, **native_inputs}.items())
            request = MixtureRequest(
                fixed.expert_set.fingerprint,
                fixed.fingerprint,
                fold_id,
                sample.fingerprint,
                tuple(reversed(grid)) if reverse else grid,
                (),
                sample.timestamp_ns,
            )
            point_outputs.append(engine.forecast(request).fingerprint)
            learned_grid = tuple((i, ext_inputs[i]) for i in train_set.expert_ids)
            learned_outputs.append(
                engine.forecast(
                    replace(
                        request,
                        expert_set_id=train_set.fingerprint,
                        gate_id=learned.fingerprint,
                        expert_inputs=learned_grid,
                    )
                ).fingerprint
            )
            prob_inputs = {
                native_probability.fingerprint: engine.bind(
                    native_probability.fingerprint, raw.fingerprint
                ).fingerprint,
                gaussian.fingerprint: external_binding(
                    repo,
                    gaussian,
                    sample,
                    distribution=DistributionParameters(
                        DistributionFamily.GAUSSIAN_LOCATION_SCALE, 0.001, 0.002
                    ),
                ),
                empirical.fingerprint: external_binding(
                    repo,
                    empirical,
                    sample,
                    distribution=DistributionParameters(
                        DistributionFamily.EMPIRICAL_RESIDUAL, 0.0, 0.003, (-0.002, 0.0, 0.005)
                    ),
                ),
            }
            probability_outputs.append(
                engine.forecast(
                    replace(
                        request,
                        expert_set_id=probability.expert_set.fingerprint,
                        gate_id=probability.fingerprint,
                        expert_inputs=tuple(prob_inputs.items()),
                    )
                ).fingerprint
            )
        outputs.append(tuple(sorted(point_outputs)))
    return MixtureFixture(
        upstream,
        fold_id,
        fixed,
        learned_spec,
        learned,
        probability,
        tuple(sorted(rows)),
        outputs[0],
        outputs[1],
        tuple(sorted(learned_outputs)),
        tuple(sorted(probability_outputs)),
    )


def demonstration(repo: MixtureRepository) -> tuple[tuple[str, object], ...]:
    f = build_fixture(repo)
    engine = MixtureEngine(repo)
    first = repo.get(MixtureForecast, f.forecast_ids[0])
    sample = repo.get(ResearchSample, first.request.sample_id)
    steps: list[tuple[str, object]] = []

    def record(name: str, value: object) -> None:
        steps.append((name, value))

    for e in f.fixed.expert_set.experts:
        record("independent expert:" + e.kind.value, e.fingerprint)
    record("fixed causal mixture", first.value)
    record("exact contributions", tuple(c.contribution for c in first.contributions))
    micro = next(
        e
        for e in f.learned_spec.expert_set.experts
        if e.kind is ExpertKind.EXTERNAL_MICROSTRUCTURE
    )
    late = external_binding(repo, micro, sample, 0.0, received=sample.timestamp_ns + 1)
    late_gate = fixed_gate(
        repo, f.learned_spec.expert_set.experts, ExpertMissingPolicy.DROP_AND_RENORMALIZE
    )
    grid = tuple(
        (i, late if i == micro.fingerprint else b)
        for i, b in first.request.expert_inputs
        if i in late_gate.expert_set.expert_ids
    )
    request = replace(
        first.request,
        expert_set_id=late_gate.expert_set.fingerprint,
        gate_id=late_gate.fingerprint,
        expert_inputs=grid,
    )
    dropped = engine.forecast(request)
    assert any(c.reason == "not-available-by-origin" for c in dropped.contributions)
    record("late expert excluded", True)
    record(
        "declared drop and renormalization",
        tuple(c.effective_weight for c in dropped.contributions),
    )
    fail = fixed_gate(repo, f.learned_spec.expert_set.experts)
    try:
        engine.forecast(
            replace(
                request, expert_set_id=fail.expert_set.fingerprint, gate_id=fail.fingerprint
            )
        )
    except ContractError:
        record("missing FAIL", True)
    context = next(
        e for e in f.learned_spec.expert_set.experts if e.kind is ExpertKind.EXTERNAL_CONTEXT
    )
    fallback = fixed_gate(
        repo,
        f.learned_spec.expert_set.experts,
        ExpertMissingPolicy.USE_DECLARED_FALLBACK,
        context.fingerprint,
    )
    fallback_forecast = engine.forecast(
        replace(
            request, expert_set_id=fallback.expert_set.fingerprint, gate_id=fallback.fingerprint
        )
    )
    assert fallback_forecast.fallback_id == context.fingerprint
    record("exact declared fallback", fallback_forecast.fallback_id)
    record("single TRAIN-only learned gate", f.learned.weights)
    record("exact admitted TRAIN rows", len(f.training_ids))
    from typing import TypeVar
    from unittest.mock import patch

    from afre.schema import Artifact
    from afre.target_engine.models import TargetVintage

    A = TypeVar("A", bound=Artifact)
    admitted = {row.target_id for row in f.learned.rows}
    original_get = repo.get

    def changed_heldout(cls: type[A], identity: str) -> A:
        value = original_get(cls, identity)
        if isinstance(value, TargetVintage) and identity not in admitted:
            return replace(value, value=99.0)
        return value

    with patch.object(repo, "get", changed_heldout):
        assert engine.fit(f.learned_spec, f.training_ids, 40, 40, 40) == f.learned
    record("TEST perturbation cannot change fitted gate", True)
    record("learned convergence residual", f.learned.convergence_residual)
    record("target-free fitted application", len(f.learned_ids))
    probability = next(
        repo.get(MixtureForecast, i)
        for i in f.probability_ids
        if repo.get(MixtureForecast, i).partition is Partition.VALIDATION
    )
    assert probability.distribution is not None
    from afre.mixture.probabilistic import (
        mixture_cdf,
        mixture_expectation,
        mixture_quantile,
        mixture_threshold,
        mixture_variance,
    )

    record("finite probability components", len(probability.distribution.components))
    record("weighted CDF", mixture_cdf(probability.distribution, 0.0))
    record(
        "exact threshold probability",
        mixture_threshold(
            probability.distribution, ThresholdRequest(0.0, ThresholdComparison.GT)
        ),
    )
    record("mixture expectation", mixture_expectation(probability.distribution))
    record("total mixture variance", mixture_variance(probability.distribution))
    try:
        mixture_quantile(probability.distribution, 0.5)
    except ContractError:
        record("quantile inversion unsupported; no averaging", True)
    evaluation = engine.evaluate(f.forecast_ids, 100, 100)
    record(
        "matched expert truth intersections",
        tuple(len(c.sample_truth_ids) for c in evaluation.comparisons),
    )
    diagnostic = engine.diagnostics(evaluation.fingerprint)
    record("correlation/disagreement", len(diagnostic.correlations))
    record("effective expert count", diagnostic.mean_effective_expert_count)
    record("availability/contribution diagnostics", len(diagnostic.experts))
    rank = engine.rank(f.upstream.upstream.spec, f.forecast_ids, f.upstream.upstream.group_refs)
    record("same-origin mixture ranks", rank.fingerprint)
    ranked = engine.evaluate_rank(rank.fingerprint, 100, 100)
    record("matched mixture IC", ranked.cross_section_evaluation_id)
    test = engine.evaluate(f.test_ids, 100, 100, "mixture-demo-TEST")
    record("explicit TEST evidence", test.test_evaluation_id)
    from examples.mixture_horizon_fixture import horizon_mixtures

    horizons = horizon_mixtures(repo)
    record("separate actual 1h/1d mixture gates", tuple(h[0].request.gate_id for h in horizons))
    old_gate = canonical_json(f.learned)
    drift = engine.drift(
        diagnostic.fingerprint, engine.diagnostics(test.fingerprint).fingerprint, 100
    )
    assert canonical_json(repo.get(GateModelArtifact, f.learned.fingerprint)) == old_gate
    record("descriptive drift; no refit", drift.state)
    record(
        "dedicated calibration assessment",
        engine.assess_calibration(first.fingerprint, (), 100).status.value,
    )
    old = canonical_json(first)
    correction = external_binding(repo, micro, sample, 0.001, revision="2")
    corrected = engine.forecast(
        replace(
            first.request,
            expert_inputs=tuple(
                (i, correction if i == micro.fingerprint else b)
                for i, b in first.request.expert_inputs
            ),
        )
    )
    assert (
        corrected.fingerprint != first.fingerprint
        and canonical_json(repo.get(MixtureForecast, first.fingerprint)) == old
    )
    record("corrected expert creates new mixture", corrected.fingerprint)
    record("old expert and mixture bytes immutable", True)
    audit = engine.audit_lineage(ranked.fingerprint)
    record("bounded unified lineage", len(audit.evidence_ids))
    record(
        "safe immutable persistence",
        repo._connection.execute("PRAGMA user_version").fetchone()[0],
    )
    assert len(steps) >= 33
    return tuple(steps)


def main() -> None:
    with TemporaryDirectory() as folder:
        path = Path(folder) / "mixture.sqlite"
        with MixtureRepository(path) as repo:
            steps = demonstration(repo)
            payloads = dict(
                repo._connection.execute("SELECT fingerprint,payload FROM mix_artifacts")
            )
            repo.audit()
        with MixtureRepository(path) as repo:
            assert (
                dict(repo._connection.execute("SELECT fingerprint,payload FROM mix_artifacts"))
                == payloads
            )
            repo.audit()
        for number, (name, value) in enumerate(steps, 1):
            print(f"{number:02d}. {name}: {value}")
        print("Restart: byte-identical immutable expert/gate/mixture artifacts")


if __name__ == "__main__":
    main()
