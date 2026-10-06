"""Explicit causal synthetic cross-domain research, with immutable TRAIN/held-out evidence."""

import math
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypeVar
from unittest.mock import patch

from afre.cross_sectional.engine import CrossSectionEngine
from afre.cross_sectional.external import ExternalSignal
from afre.event_conditioned.engine import EventEngine
from afre.mixture import ExpertKind
from afre.nonlinear import (
    DenominatorPolicy,
    FittedTransformArtifact,
    InteractionDefinition,
    InteractionMatrix,
    InteractionSet,
    InteractionTrainingRow,
    InteractionTransform,
    KnotPolicy,
    NonlinearEngine,
    NonlinearFamily,
    NonlinearForecast,
    NonlinearInput,
    NonlinearModelArtifact,
    NonlinearModelSpec,
    NonlinearRepository,
    ScalarFeatureDefinition,
    TransformParameters,
    TreeParameters,
)
from afre.nonlinear.definitions import output_unit
from afre.nonlinear.transforms import transform_value
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.regime_conditioned.engine import RegimeEngine
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.target_engine.models import TargetVintage
from examples.cross_sectional_demo import external
from examples.event_conditioned_demo import event
from examples.mixture_demo import MixtureFixture, external_binding, external_reference
from examples.mixture_demo import build_fixture as mixture_fixture
from examples.regime_conditioned_demo import snapshot, taxonomy


def signal(
    sample: ResearchSample, name: str, value: float, revision: str = "1"
) -> ExternalSignal:
    return replace(
        external(sample.security, sample.timestamp_ns, value),
        signal_name=name,
        signal_version=revision,
        signal_semantics="synthetic-causal-scalar-v1",
        unit="1",
    )


@dataclass(frozen=True)
class NonlinearFixture:
    upstream: MixtureFixture
    specs: tuple[NonlinearModelSpec, ...]
    models: tuple[NonlinearModelArtifact, ...]
    train_ids: tuple[str, ...]
    validation_ids: tuple[str, ...]
    test_ids: tuple[str, ...]
    forecast_ids: tuple[tuple[str, ...], ...]
    test_forecast_ids: tuple[str, ...]
    transform_ids: tuple[str, ...]


def build_fixture(
    repo: NonlinearRepository, reverse: bool = False, upstream: MixtureFixture | None = None
) -> NonlinearFixture:
    upstream = upstream or mixture_fixture(repo, reverse)
    target = upstream.fixed.expert_set.target
    engine = NonlinearEngine(repo)
    tax = taxonomy()
    RegimeEngine(repo).publish_taxonomy(tax)
    expert = external_reference(target, ExpertKind.EXTERNAL_GENERIC, "interaction-expert")
    packets: dict[Partition, list[NonlinearInput]] = {
        Partition.TRAIN: [],
        Partition.VALIDATION: [],
        Partition.TEST: [],
    }
    for partition in packets:
        samples = repo.partition_samples(upstream.fold_id, partition)
        for sample in tuple(reversed(samples)) if reverse else samples:
            if sample.target_definition_id != target.fingerprint:
                continue
            assert sample.origin is not None
            security = int(sample.security.value)
            x = 1.0 + security + sample.timestamp_ns / 100
            context_number = 1.0 + (security % 3) / 2
            neutral = tuple(
                signal(sample, name, number)
                for name, number in (
                    ("microstructure.signal", x),
                    ("context.signal", context_number),
                    ("options.skew", 0.1 + security / 20),
                )
            )
            scalar_ids = []
            for source in tuple(reversed(neutral)) if reverse else neutral:
                CrossSectionEngine(repo).publish_external(source)
                scalar_ids.append(engine.scalar(source.fingerprint, sample.origin).fingerprint)
            e = event(
                sample, "nonlinear-event-" + sample.fingerprint, score=0.2 + security / 20
            )
            EventEngine(repo).publish_event(e)
            scalar_ids.append(
                engine.scalar(e.fingerprint, sample.origin, "surprise").fingerprint
            )
            s = snapshot(tax, sample, soft=(0.25 + security / 10, 0.75 - security / 10))
            RegimeEngine(repo).publish_snapshot(s)
            scalar_ids.append(engine.scalar(s.fingerprint, sample.origin, "A").fingerprint)
            binding = external_binding(repo, expert, sample, x / 100)
            scalar_ids.append(engine.scalar(binding, sample.origin).fingerprint)
            for vintage_id in sample.feature_vintage_ids:
                scalar_ids.append(engine.scalar(vintage_id, sample.origin).fingerprint)
            packets[partition].append(
                engine.input(
                    sample.fingerprint,
                    tuple(reversed(scalar_ids)) if reverse else tuple(scalar_ids),
                )
            )
    first = packets[Partition.TRAIN][0]
    by_name = {
        s.definition.source_key[3]: s.definition
        for s in first.scalars
        if s.definition.kind.value == "external_signal"
    }
    micro, context, options = (
        by_name[n] for n in ("microstructure.signal", "context.signal", "options.skew")
    )
    event_def = next(
        s.definition for s in first.scalars if s.definition.kind.value == "event_attribute"
    )
    regime_def = next(
        s.definition for s in first.scalars if s.definition.kind.value == "regime_probability"
    )
    expert_def = next(
        s.definition for s in first.scalars if s.definition.kind.value == "expert_point"
    )
    ordinary = tuple(
        s.definition for s in first.scalars if s.definition.kind.value == "feature"
    )

    def definition(
        name: str,
        transform: InteractionTransform,
        features: tuple[ScalarFeatureDefinition, ...],
        params: TransformParameters | None = None,
    ) -> InteractionDefinition:
        return InteractionDefinition(
            name,
            features,
            transform,
            params or TransformParameters(),
            name,
            output_unit(transform, features),
        )

    definitions = (
        definition("micro-context", InteractionTransform.PRODUCT, (micro, context)),
        definition("options-context", InteractionTransform.PRODUCT, (options, context)),
        definition("event-regime", InteractionTransform.PRODUCT, (event_def, regime_def)),
        definition("expert-state", InteractionTransform.PRODUCT, (expert_def, regime_def)),
        definition(
            "micro-ratio",
            InteractionTransform.RATIO,
            (micro, context),
            TransformParameters(denominator=DenominatorPolicy.FAIL_ON_ZERO),
        ),
        definition("signed-log", InteractionTransform.LOG1P_SIGNED, (micro,)),
        definition(
            "piecewise",
            InteractionTransform.PIECEWISE_LINEAR,
            (micro,),
            TransformParameters(
                knot_policy=KnotPolicy.TRAIN_QUANTILES,
                quantile_levels=(0.0, 0.5, 1.0),
                ordinates=(0.0, 0.5, 1.0),
            ),
        ),
        *(
            definition("ordinary-" + str(i), InteractionTransform.IDENTITY, (f,))
            for i, f in enumerate(ordinary)
        ),
    )
    interaction_set = InteractionSet(
        tuple(reversed(definitions)) if reverse else definitions, target
    )
    specs = tuple(
        NonlinearModelSpec(
            interaction_set,
            family,
            () if family is NonlinearFamily.LINEAR_ON_INTERACTIONS else (micro, context),
            upstream.fold_id,
            40,
            0,
            tree=TreeParameters()
            if family is NonlinearFamily.SHALLOW_REGRESSION_TREE
            else None,
            ridge_penalty=0.0 if family is NonlinearFamily.SHALLOW_REGRESSION_TREE else 0.01,
        )
        for family in NonlinearFamily
    )
    train_ids = tuple(p.fingerprint for p in packets[Partition.TRAIN])
    models = []
    forecasts = []
    transform_ids: tuple[str, ...] = ()
    for spec in specs:
        piece = next(
            d for d in spec.interaction_set.definitions if d.interaction_id == "piecewise"
        )
        state = engine.fit_transform(spec, piece, train_ids, 40, 40, 40)
        transform_ids = (state.fingerprint,)
        matrix = engine.matrix(spec, train_ids, transform_ids, 40)
        model = engine.fit(spec, matrix.fingerprint, 40, 40, 40)
        models.append(model)
        ids = []
        for packet in packets[Partition.VALIDATION]:
            if packet.origin.timestamp_ns != 60:
                continue
            base = next(
                (
                    p
                    for p in upstream.upstream.upstream.upstream.deployment[0]
                    if isinstance(p, ProbabilisticForecast)
                    and p.input.sample_id == packet.sample_id
                ),
                None,
            )
            ids.append(
                engine.predict(
                    model.fingerprint,
                    packet.fingerprint,
                    packet.origin.timestamp_ns,
                    base.fingerprint if base else None,
                ).fingerprint
            )
        forecasts.append(tuple(ids))
    test_ids = tuple(
        engine.predict(models[0].fingerprint, p.fingerprint, p.origin.timestamp_ns).fingerprint
        for p in packets[Partition.TEST]
    )
    return NonlinearFixture(
        upstream,
        specs,
        tuple(models),
        train_ids,
        tuple(p.fingerprint for p in packets[Partition.VALIDATION]),
        tuple(p.fingerprint for p in packets[Partition.TEST]),
        tuple(forecasts),
        test_ids,
        transform_ids,
    )


def demonstration(repo: NonlinearRepository) -> tuple[tuple[str, object], ...]:
    fixture = build_fixture(repo)
    engine = NonlinearEngine(repo)
    rows: list[tuple[str, object]] = []
    first = repo.get(NonlinearForecast, fixture.forecast_ids[0][0])
    for model, ids in zip(fixture.models, fixture.forecast_ids, strict=True):
        evaluation = engine.evaluate(ids, 100, 100)
        rows.append((model.family.value, evaluation.metrics))
    rank = engine.rank(
        fixture.upstream.upstream.upstream.spec,
        fixture.forecast_ids[0],
        fixture.upstream.upstream.upstream.group_refs,
    )
    ranked = engine.evaluate_rank(rank.fingerprint, 100, 100)
    test = engine.evaluate(
        fixture.test_forecast_ids, 100, 100, test_identity="nonlinear-demo-TEST"
    )
    matched = engine.evaluate(
        fixture.forecast_ids[1],
        100,
        100,
        tuple((repo.get(NonlinearForecast, i).sample_id, i) for i in fixture.forecast_ids[0]),
    )
    spec = fixture.specs[0]
    alternate = replace(spec, seed=1)
    engine.publish_spec(alternate)
    piece = next(
        d for d in alternate.interaction_set.definitions if d.interaction_id == "piecewise"
    )
    state = engine.fit_transform(alternate, piece, fixture.train_ids, 40, 40, 40)
    matrix = engine.matrix(alternate, fixture.train_ids, (state.fingerprint,), 40)
    other = engine.fit(alternate, matrix.fingerprint, 40, 40, 40)
    stability = engine.stability((fixture.models[0].fingerprint, other.fingerprint), 100)
    audit = engine.audit_lineage(first.fingerprint)
    inputs = repo.get(NonlinearInput, first.input_id)
    by_kind = {s.definition.kind.value: s for s in inputs.scalars}
    definitions = {d.interaction_id: d for d in spec.interaction_set.definitions}
    state = repo.get(FittedTransformArtifact, fixture.models[0].transform_ids[0])
    product = engine.apply(definitions["micro-context"], inputs.fingerprint, 60)
    ratio = engine.apply(definitions["micro-ratio"], inputs.fingerprint, 60)
    log = engine.apply(definitions["signed-log"], inputs.fingerprint, 60)
    assert transform_value(definitions["micro-context"], (2.0, 3.0)) == (6.0, False)
    assert transform_value(definitions["signed-log"], (-3.0,))[0] == -math.log(4.0)
    try:
        transform_value(definitions["micro-ratio"], (2.0, 0.0))
    except ContractError:
        ratio_zero_rejected = True
    else:
        raise AssertionError("ratio silently used zero denominator")
    A = TypeVar("A", bound=Artifact)
    original = repo.get
    train_matrix = repo.get(InteractionMatrix, fixture.models[2].matrix_id)
    train_targets = {r.target_id for r in train_matrix.rows}

    def heldout_change(cls: type[A], identity: str) -> A:
        value = original(cls, identity)
        if isinstance(value, TargetVintage) and identity not in train_targets:
            return replace(value, value=999.0)
        return value

    with patch.object(repo, "get", heldout_change):
        assert (
            engine.fit_transform(spec, definitions["piecewise"], fixture.train_ids, 40, 40, 40)
            == state
        )
        assert (
            engine.fit(fixture.specs[2], train_matrix.fingerprint, 40, 40, 40)
            == fixture.models[2]
        )

    def guard(cls: type[A], identity: str) -> A:
        assert cls not in (TargetVintage, InteractionMatrix, InteractionTrainingRow), (
            "target read at prediction"
        )
        return original(cls, identity)

    with patch.object(repo, "get", guard):
        assert (
            engine.predict(
                first.model_id,
                first.input_id,
                60,
                first.probability.base_forecast_id if first.probability else None,
            )
            == first
        )
    external_scalar = next(
        v
        for v in inputs.scalars
        if v.definition.kind.value == "external_signal"
        and v.definition.source_key[3] == "microstructure.signal"
    )
    source = repo.get(ExternalSignal, external_scalar.source_id)
    assert isinstance(source.value, (int, float))
    corrected = replace(source, value=float(source.value) + 0.1)
    CrossSectionEngine(repo).publish_external(corrected)
    revised = engine.scalar(corrected.fingerprint, inputs.origin)
    packet = engine.input(
        inputs.sample_id,
        tuple(
            revised.fingerprint if v == external_scalar else v.fingerprint
            for v in inputs.scalars
        ),
    )
    new_product = engine.apply(definitions["micro-context"], packet.fingerprint, 60)
    assert new_product.fingerprint != product.fingerprint
    assert repo.get_any(product.fingerprint) == product
    # Reversing supplied semantic sets/inputs/requests retains exact bytes.
    assert (
        replace(
            spec.interaction_set, definitions=tuple(reversed(spec.interaction_set.definitions))
        )
        == spec.interaction_set
    )
    assert (
        engine.input(inputs.sample_id, tuple(v.fingerprint for v in reversed(inputs.scalars)))
        == inputs
    )
    assert engine.evaluate(
        tuple(reversed(fixture.forecast_ids[0])), 100, 100
    ) == engine.evaluate(fixture.forecast_ids[0], 100, 100)
    cross = tuple(
        engine.apply(definitions[name], inputs.fingerprint, 60).value
        for name in ("event-regime", "micro-context", "options-context", "expert-state")
    )
    steps: tuple[tuple[str, object], ...] = (
        (
            "01 ordinary causal features",
            sum(v.definition.kind.value == "feature" for v in inputs.scalars),
        ),
        ("02 event scalar", by_kind["event_attribute"].value),
        ("03 filtered regime scalar", by_kind["regime_probability"].value),
        ("04 neutral microstructure", external_scalar.source_id),
        ("05 neutral context", definitions["micro-context"].fingerprint),
        ("06 neutral options", definitions["options-context"].fingerprint),
        ("07 causal AFRE-12 expert output", by_kind["expert_point"].source_id),
        ("08 explicit product oracle", 6.0),
        ("09 ratio/zero rejection", (ratio.value, ratio_zero_rejected)),
        ("10 signed-log oracle", log.value),
        ("11 TRAIN piecewise knots", state.knots),
        ("12 held-out cannot change knots", True),
        ("13 event×regime", cross[0]),
        ("14 microstructure×context", cross[1]),
        ("15 options×context", cross[2]),
        ("16 expert×state", cross[3]),
        ("17 exact TRAIN matrix", train_matrix.fingerprint),
        ("18 linear-on-interactions", fixture.models[0].fingerprint),
        ("19 linear-plus-interactions", fixture.models[1].fingerprint),
        ("20 bounded shallow tree", fixture.models[2].fingerprint),
        ("21 held-out labels cannot change tree", True),
        ("22 target-free prediction", first.fingerprint),
        ("23 compatible probability location shift", first.probability is not None),
        ("24 same-origin ranking", rank.fingerprint),
        ("25 exact matched truths", matched.fingerprint),
        ("26 descriptive metric deltas", matched.deltas),
        ("27 arithmetic contributions", first.contributions),
        ("28 exact tree path", repo.get(NonlinearForecast, fixture.forecast_ids[2][0]).path),
        ("29 descriptive stability", stability.fingerprint),
        (
            "30 diagnostics cannot prune",
            repo.get(NonlinearModelArtifact, fixture.models[0].fingerprint)
            == fixture.models[0],
        ),
        ("31 explicit source correction", corrected.fingerprint),
        ("32 old interaction bytes unchanged", repo.get_any(product.fingerprint) == product),
        ("33 corrected interaction new identity", new_product.fingerprint),
        ("35 insertion/request deterministic replay", True),
        ("36 bounded audit/lineage", len(audit.node_ids)),
        ("TEST evidence", test.test_evaluation_id),
        ("rank IC", ranked.fingerprint),
        (
            "calibration compatibility",
            engine.assess_calibration(
                first.fingerprint, fixture.forecast_ids[0], 100
            ).status.value,
        ),
    )
    rows.extend(steps)
    return tuple(rows)


def main() -> None:
    with TemporaryDirectory(prefix="afre-nonlinear-") as directory:
        path = Path(directory) / "nonlinear.sqlite"
        with NonlinearRepository(path) as repo:
            results = demonstration(repo)
            identities = tuple(
                r[0]
                for r in repo._connection.execute(
                    "SELECT fingerprint FROM nl_artifacts ORDER BY fingerprint"
                )
            )
            before = tuple(canonical_json(repo.get_any(i)) for i in identities)
            print(results)
        with NonlinearRepository(path) as repo:
            assert tuple(canonical_json(repo.get_any(i)) for i in identities) == before
            print("34 persist/restart", len(identities), "artifacts unchanged")


if __name__ == "__main__":
    main()
