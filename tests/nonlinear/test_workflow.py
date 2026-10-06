"""Causal integration, exact cross-domain effects, matched metrics and unchanged models."""

from dataclasses import replace

import pytest

from afre.cross_sectional.external import ExternalSignal
from afre.mixture import MixtureForecast
from afre.nonlinear import (
    FittedTransformArtifact,
    InteractionDefinition,
    InteractionSet,
    InteractionTransform,
    NonlinearFamily,
    NonlinearForecast,
    NonlinearInput,
    NonlinearModelArtifact,
    NonlinearPreprocessing,
    ScalarSourceKind,
)
from afre.probabilistic.artifacts import ProbabilisticForecast
from afre.probabilistic.distributions import conditional_variance, expected_value, quantile
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.statistical_models.schema import MetricName
from tests.nonlinear.conftest import Case


@pytest.mark.parametrize("family", list(NonlinearFamily))
def test_model_family(case: Case, family: NonlinearFamily) -> None:
    index = list(NonlinearFamily).index(family)
    model = case.fixture.models[index]
    assert model.train_sample_ids and model.training_squared_error >= 0
    forecast = case.repo.get(NonlinearForecast, case.fixture.forecast_ids[index][0])
    if family is NonlinearFamily.SHALLOW_REGRESSION_TREE:
        assert model.nodes and not model.coefficients and forecast.path[-1].branch == "leaf"
    else:
        assert model.coefficients and not model.nodes
        assert model.intercept + sum(v for _, v in forecast.contributions) == pytest.approx(
            forecast.value
        )


@pytest.mark.parametrize(
    "name", ["event-regime", "micro-context", "options-context", "expert-state"]
)
def test_exact_cross_domain_product(case: Case, name: str) -> None:
    spec = case.fixture.specs[0]
    definition = next(d for d in spec.interaction_set.definitions if d.interaction_id == name)
    scalar_map = {s.definition: s for s in case.inputs.scalars}
    expected = 1.0
    for f in definition.inputs:
        value = scalar_map[f].value
        assert value is not None
        expected *= value
    output = case.engine.apply(
        definition, case.inputs.fingerprint, case.inputs.origin.timestamp_ns
    )
    assert output.value == pytest.approx(expected)
    assert output.available_ns >= max(scalar_map[f].available_ns for f in definition.inputs)


def test_train_quantiles_independent(case: Case) -> None:
    model = case.fixture.models[0]
    state = case.repo.get(FittedTransformArtifact, model.transform_ids[0])
    definition = case.repo.get(InteractionDefinition, state.definition_id)
    raw_values = tuple(
        next(
            s.value
            for s in case.repo.get(NonlinearInput, i).scalars
            if s.definition == definition.inputs[0]
        )
        for i in state.train_input_ids
    )
    values = sorted(v for v in raw_values if v is not None)
    assert len(values) == 12
    assert state.knots == (values[0], (values[5] + values[6]) / 2, values[-1])
    assert state.train_sample_ids == model.train_sample_ids


def test_probability_shape_and_quantiles(case: Case) -> None:
    forecast = case.forecast
    assert forecast.probability is not None
    base = case.repo.get(ProbabilisticForecast, forecast.probability.base_forecast_id)
    view = forecast.probability
    assert view.distribution.scale == base.distribution.scale
    assert view.distribution.samples == base.distribution.samples
    assert expected_value(view.distribution) == pytest.approx(forecast.value)
    assert conditional_variance(view.distribution) == conditional_variance(base.distribution)
    assert all(
        q.value == pytest.approx(quantile(view.distribution, q.level)) for q in view.quantiles
    )
    assert canonical_json(base) == canonical_json(case.repo.get_any(base.fingerprint))


def test_matched_comparison_and_mixture_baseline(case: Case) -> None:
    baselines = tuple(
        (case.repo.get(NonlinearForecast, i).sample_id, i) for i in case.fixture.forecast_ids[0]
    )
    result = case.engine.evaluate(case.fixture.forecast_ids[1], 100, 100, baselines)
    assert tuple((p.sample_id, p.target_id) for p in result.pairs)
    by_name = {m.name: m.value for m in result.metrics}
    mse = sum((p.prediction - p.truth) ** 2 for p in result.pairs) / len(result.pairs)
    assert by_name[MetricName.MSE] == pytest.approx(mse)
    delta = next(m.value for m in result.deltas if m.name is MetricName.MSE)
    base_mse = sum(
        (p.baseline - p.truth) ** 2 for p in result.pairs if p.baseline is not None
    ) / len(result.pairs)
    assert delta == pytest.approx(mse - base_mse)
    mixtures = tuple(
        (case.repo.get(MixtureForecast, i).request.sample_id, i)
        for i in case.fixture.upstream.forecast_ids
    )
    assert len(
        case.engine.evaluate(case.fixture.forecast_ids[0], 100, 100, mixtures).pairs
    ) == len(result.pairs)
    with pytest.raises(ContractError, match="grid"):
        case.engine.evaluate(case.fixture.forecast_ids[0], 100, 100, baselines[:-1])


def test_event_regime_cohorts(case: Case) -> None:
    result = case.engine.evaluate(case.fixture.forecast_ids[0], 100, 100)
    names = {name for name, _ in result.cohorts}
    assert any(n.startswith("event:") for n in names)
    assert "regime-kind:soft" in names and "regime-active:A" in names
    assert result.probability_scores


def test_ranking_and_ic(case: Case) -> None:
    cs = case.fixture.upstream.upstream.upstream
    rank = case.engine.rank(cs.spec, case.fixture.forecast_ids[0], cs.group_refs)
    result = case.engine.evaluate_rank(rank.fingerprint, 100, 100)
    assert result.ranking_id == rank.fingerprint
    assert case.engine.audit_lineage(result.fingerprint).node_ids


def test_stability_no_prune(case: Case) -> None:
    spec = replace(case.fixture.specs[0], seed=7)
    piece = next(d for d in spec.interaction_set.definitions if d.interaction_id == "piecewise")
    state = case.engine.fit_transform(spec, piece, case.fixture.train_ids, 40, 40, 40)
    matrix = case.engine.matrix(spec, case.fixture.train_ids, (state.fingerprint,), 40)
    second = case.engine.fit(spec, matrix.fingerprint, 40, 40, 40)
    first = case.fixture.models[0]
    before = canonical_json(first)
    result = case.engine.stability((first.fingerprint, second.fingerprint), 100)
    assert result.coefficient_sign_consistency == (1.0,) * len(first.columns)
    assert result.coefficient_magnitude_drift == (0.0,) * len(first.columns)
    assert canonical_json(case.repo.get(NonlinearModelArtifact, first.fingerprint)) == before
    assert (
        case.repo.get(InteractionSet, spec.interaction_set.fingerprint) == spec.interaction_set
    )
    assert case.engine.audit_lineage(result.fingerprint).node_ids


def test_standardize_train_only(case: Case) -> None:
    source = case.fixture.specs[0]
    # Standardization retains exact TRAIN values and rejects zero scales.
    product = next(
        d for d in source.interaction_set.definitions if d.interaction_id == "micro-context"
    )
    full = replace(source, preprocessing=NonlinearPreprocessing.STANDARDIZE)
    piece = next(d for d in full.interaction_set.definitions if d.interaction_id == "piecewise")
    state = case.engine.fit_transform(full, piece, case.fixture.train_ids, 40, 40, 40)
    matrix = case.engine.matrix(full, case.fixture.train_ids, (state.fingerprint,), 40)
    model = case.engine.fit(full, matrix.fingerprint, 40, 40, 40)
    assert model.centers == pytest.approx(
        tuple(
            sum(r.values[j] for r in matrix.rows) / len(matrix.rows)
            for j in range(len(matrix.columns))
        )
    )
    assert all(s > 0 for s in model.scales)
    forecast = case.engine.predict(
        model.fingerprint, case.inputs.fingerprint, case.inputs.origin.timestamp_ns
    )
    assert forecast.contributions
    assert product.fingerprint in model.columns


def test_duplicate_interactions_and_revision_identity(case: Case) -> None:
    definition = case.fixture.specs[0].interaction_set.definitions[0]
    with pytest.raises(ContractError, match="duplicate semantic"):
        InteractionSet(
            (definition, replace(definition, interaction_id="alias", output_name="alias")),
            case.fixture.specs[0].target,
        )
    with pytest.raises(ContractError, match="duplicate"):
        InteractionSet((definition, definition), case.fixture.specs[0].target)
    scalar = next(
        s for s in case.inputs.scalars if s.definition.kind is ScalarSourceKind.EXTERNAL_SIGNAL
    )
    source = case.repo.get(ExternalSignal, scalar.source_id)
    from afre.cross_sectional.engine import CrossSectionEngine

    assert isinstance(source.value, (int, float))
    revised = replace(source, value=float(source.value) + 1.0)
    CrossSectionEngine(case.repo).publish_external(revised)
    new = case.engine.scalar(revised.fingerprint, scalar.origin)
    packet = case.engine.input(
        case.inputs.sample_id,
        tuple(new.fingerprint if s == scalar else s.fingerprint for s in case.inputs.scalars),
    )
    interaction = next(
        d
        for d in case.fixture.specs[0].interaction_set.definitions
        if scalar.definition in d.inputs and d.transform is InteractionTransform.PRODUCT
    )
    old = case.engine.apply(interaction, case.inputs.fingerprint, scalar.origin.timestamp_ns)
    corrected = case.engine.apply(interaction, packet.fingerprint, scalar.origin.timestamp_ns)
    assert old.fingerprint != corrected.fingerprint and old.value != corrected.value
    assert canonical_json(old) == canonical_json(case.repo.get_any(old.fingerprint))
