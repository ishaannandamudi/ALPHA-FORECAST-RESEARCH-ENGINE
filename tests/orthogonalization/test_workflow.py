"""Exact sources, PIT panels, frozen comparisons and descriptive stability."""

from dataclasses import replace

import pytest

from afre.cross_sectional.definitions import CrossSectionSpec
from afre.feature_store.models import FeatureVintage
from afre.mixture import MixtureForecast
from afre.mixture.experts import ExpertForecastBinding
from afre.orthogonalization import (
    OrthogonalizationMode,
    OrthogonalQuality,
    SignalObservation,
    SignalSourceType,
)
from afre.orthogonalization.projection import numeric
from afre.orthogonalization.sources import reference_for
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from afre.serialization import canonical_json
from afre.statistical_models.schema import MetricName
from afre.uncertainty import ForecastUncertaintyDecomposition
from afre.uncertainty.sources import source_for
from examples.orthogonalization_fixture import build_rows, generic_source
from examples.orthogonalization_oracles import pearson
from tests.orthogonalization.conftest import Case


@pytest.mark.parametrize(
    "name", ["event", "hard-regime", "soft-regime", "mixture", "nonlinear", "tree", "sequence"]
)
def test_native_outputs(case: Case, name: str) -> None:
    identity = case.fixture.upstream.ids(name)[0]
    source = source_for(case.repo, identity)
    ref = reference_for(case.repo, identity, source.sample_id, "native-" + name)
    value = case.engine.bind(ref, identity, source.sample_id)
    assert value.value == source.prediction
    assert ref.target == case.fixture.spec.target
    assert value.available_ns <= value.origin.availability_cutoff_ns
    with pytest.raises(ContractError):
        case.engine.bind(replace(ref, unit="wrong"), identity, source.sample_id)


@pytest.mark.parametrize("selector", ["total_predictive", "parameter"])
def test_uncertainty_exact_component(case: Case, selector: str) -> None:
    ids = case.fixture.upstream.results("gaussian")
    value = case.repo.get(ForecastUncertaintyDecomposition, ids[0])
    ref = reference_for(case.repo, value.fingerprint, value.sample_id, "diagnostic", selector)
    for identity in ids:
        d = case.repo.get(ForecastUncertaintyDecomposition, identity)
        obs = case.engine.bind(ref, identity, d.sample_id)
        assert obs.value == next(c.value for c in d.components if c.component.value == selector)
    assert ref.source_type is SignalSourceType.UNCERTAINTY and ref.unit.startswith("target")
    with pytest.raises(ContractError):
        reference_for(
            case.repo, value.fingerprint, value.sample_id, "bad", "model_specification"
        )


def test_expert_output(case: Case) -> None:
    mix = case.repo.get(MixtureForecast, case.fixture.upstream.ids("mixture")[0])
    for _, identity in mix.request.expert_inputs:
        assert identity is not None
        binding = case.repo.get(ExpertForecastBinding, identity)
        ref = reference_for(
            case.repo, identity, mix.request.sample_id, "expert-" + binding.expert_id
        )
        obs = case.engine.bind(ref, identity, mix.request.sample_id)
        assert obs.quality is OrthogonalQuality.AVAILABLE and obs.value is not None


def test_feature_and_scalar_inputs(case: Case) -> None:
    sample = case.repo.get(
        ResearchSample, case.fixture.partition(Partition.VALIDATION)[0].sample_id
    )
    for identity in sample.feature_vintage_ids:
        raw = case.repo.get(FeatureVintage, identity)
        ref = reference_for(
            case.repo, identity, sample.fingerprint, "ordinary-" + raw.feature.definition.name
        )
        obs = case.engine.bind(ref, identity, sample.fingerprint)
        assert obs.value == raw.value and ref.target is None
    from afre.nonlinear import NonlinearInput

    packet = next(
        case.repo.get(NonlinearInput, i)
        for i in case.fixture.upstream.upstream.upstream.validation_ids
        if case.repo.get(NonlinearInput, i).sample_id == sample.fingerprint
    )
    for scalar in packet.scalars:
        ref = reference_for(
            case.repo,
            scalar.fingerprint,
            sample.fingerprint,
            "scalar-" + scalar.definition.fingerprint,
        )
        assert (
            case.engine.bind(ref, scalar.fingerprint, sample.fingerprint).value == scalar.value
        )


def test_exact_matrix_intersection_and_missing(case: Case) -> None:
    f = case.fixture
    row = f.partition(Partition.VALIDATION)[0]
    old = case.repo.get(SignalObservation, row.observation_ids[0])
    sample = case.repo.get(ResearchSample, row.sample_id)
    src = case.engine.publish_generic(generic_source(f.spec.candidate, sample, None, "missing"))
    obs = case.engine.bind(f.spec.candidate, src.fingerprint, row.sample_id)
    ids = tuple(obs.fingerprint if i == old.fingerprint else i for i in row.observation_ids)
    missing = case.engine.align(f.spec, ids)
    residual = case.engine.residual(
        f.projection.fingerprint, missing.fingerprint, row.origin.timestamp_ns
    )
    assert residual.quality is OrthogonalQuality.MISSING and residual.residual is None
    rows = (missing, *f.partition(Partition.VALIDATION)[1:])
    matrix = case.engine.matrix(f.spec.fingerprint, tuple(r.fingerprint for r in rows), 100)
    assert matrix.excluded_sample_ids == (row.sample_id,)
    assert all(m.sample_count == len(rows) - 1 for r in matrix.pearson for m in r)
    assert row.sample_id not in matrix.intersection_sample_ids
    values = (residual.fingerprint, *f.residual_ids(Partition.VALIDATION)[1:])
    evaluation = case.engine.evaluate(values, 100, 100, target_diagnostics=True)
    assert evaluation.sample_ids == matrix.intersection_sample_ids


def test_partial_frozen_common_controls(case: Case) -> None:
    f = case.fixture
    xref = next(r for r in f.spec.references if r.signal_id.endswith("-x"))
    zref = next(r for r in f.spec.references if r.signal_id.endswith("-z"))
    results = []
    for cand in (f.spec.candidate, zref):
        spec = replace(f.spec, candidate=cand, references=(xref,))
        rows = tuple(
            case.engine.align(
                spec,
                tuple(
                    i
                    for i in r.observation_ids
                    if case.repo.get(SignalObservation, i).reference_id
                    in (cand.fingerprint, xref.fingerprint)
                ),
            )
            for r in f.rows
        )
        projection = case.engine.fit(
            spec, tuple(r.fingerprint for r in rows if r.partition is Partition.TRAIN), 40
        )
        results.append(
            tuple(
                case.engine.residual(
                    projection.fingerprint, r.fingerprint, r.origin.timestamp_ns
                )
                for r in rows
                if r.partition is Partition.VALIDATION
            )
        )
    left, right = results
    p = case.engine.partial(
        tuple(v.fingerprint for v in left),
        tuple(reversed(tuple(v.fingerprint for v in right))),
        100,
    )
    a = {v.sample_id: numeric(v.residual) for v in left}
    b = {v.sample_id: numeric(v.residual) for v in right}
    assert p.pearson.value == pytest.approx(
        pearson(tuple(a[k] for k in p.sample_ids), tuple(b[k] for k in p.sample_ids))
    )
    assert len(p.sample_ids) == len(case.fixture.partition(Partition.VALIDATION))
    with pytest.raises(ContractError):
        case.engine.partial(
            tuple(v.fingerprint for v in left), tuple(v.fingerprint for v in right[:-1]), 100
        )


def test_historical_cross_sectional_and_ranking(case: Case) -> None:
    spec, rows = build_rows(
        case.repo,
        case.fixture.spec.fold_id,
        case.fixture.spec.target,
        40,
        mode=OrthogonalizationMode.CROSS_SECTIONAL_HISTORICAL,
        tag="cross",
    )
    train = tuple(r.fingerprint for r in rows if r.partition is Partition.TRAIN)
    projection = case.engine.fit(spec, train, 40)
    with pytest.raises(ContractError, match="grid"):
        case.engine.fit(spec, train[1:], 40)
    heldout = tuple(r for r in rows if r.origin.timestamp_ns == 60)
    values = tuple(
        case.engine.residual(projection.fingerprint, r.fingerprint, 60) for r in heldout
    )
    template = case.fixture.upstream.upstream.upstream.upstream.upstream.upstream.spec
    assert isinstance(template, CrossSectionSpec)
    rank = case.engine.rank(
        template,
        tuple(v.fingerprint for v in values),
        case.fixture.upstream.upstream.upstream.upstream.upstream.upstream.group_refs,
    )
    assert len(rank.entries) == 4
    assert rank.spec_id != template.fingerprint
    old = canonical_json(rank)
    from afre.cross_sectional.engine import CrossSectionEngine
    from afre.cross_sectional.groups import GroupMembership

    groups = case.fixture.upstream.upstream.upstream.upstream.upstream.upstream.group_refs
    for _, identity in groups:
        g = case.repo.get(GroupMembership, identity)
        at = 100
        newer = replace(
            g,
            group_id="later-sector",
            clocks=replace(
                g.clocks,
                afre_received_ns=at,
                afre_ingested_ns=at,
                afre_computed_ns=at,
                final_available_ns=at,
            ),
        )
        CrossSectionEngine(case.repo).publish_group(newer)
    assert (
        canonical_json(case.engine.rank(template, tuple(v.fingerprint for v in values), groups))
        == old
    )
    newer_groups = tuple(
        (key, newer.fingerprint) if key == newer.security.fingerprint else (key, identity)
        for key, identity in groups
    )
    with pytest.raises(ContractError):
        case.engine.rank(template, tuple(v.fingerprint for v in values), newer_groups)
    evaluation = case.engine.evaluate(
        tuple(v.fingerprint for v in values), 100, 100, target_diagnostics=True
    )
    assert len(evaluation.origin_information_coefficients) == 1


def test_cross_sectional_same_time_contexts_cannot_be_pooled(case: Case) -> None:
    from afre.orthogonalization.alignment import validate_cross_sectional_grid

    _, rows = build_rows(
        case.repo,
        case.fixture.spec.fold_id,
        case.fixture.spec.target,
        40,
        mode=OrthogonalizationMode.CROSS_SECTIONAL_HISTORICAL,
        tag="origin-context",
    )
    first = tuple(r for r in rows if r.origin.timestamp_ns == 60)
    validate_cross_sectional_grid(case.repo, first)
    # Even two complete eligible grids cannot become one same-origin rank-IC slice.
    second = tuple(
        replace(r, origin=replace(r.origin, build_context=r.origin.build_context + "-other"))
        for r in first
    )
    with pytest.raises(ContractError, match="one full universe/origin context"):
        validate_cross_sectional_grid(case.repo, (*first, *second))


def test_descriptive_stability_and_no_pruning(case: Case) -> None:
    e = case.engine
    before = canonical_json(case.fixture.projection)
    first = tuple(v.fingerprint for v in case.fixture.residuals if v.origin.timestamp_ns == 50)
    second = tuple(v.fingerprint for v in case.fixture.residuals if v.origin.timestamp_ns == 60)
    a, b = e.evaluate(first, 100, 100), e.evaluate(second, 100, 100)
    count = case.repo._connection.execute("SELECT count(*) FROM m_artifacts").fetchone()[0]
    stability = e.stability((a.fingerprint, b.fingerprint), 100)
    coeff = (case.fixture.projection.intercept, *case.fixture.projection.coefficients)
    assert stability.coefficient_ranges == tuple((v, v) for v in coeff)
    assert stability.residual_variance_ratios == (
        a.residual_variance_ratio,
        b.residual_variance_ratio,
    )
    assert (
        case.repo._connection.execute("SELECT count(*) FROM m_artifacts").fetchone()[0] == count
    )
    assert canonical_json(case.repo.get_any(case.fixture.projection.fingerprint)) == before
    with pytest.raises(ContractError):
        e.stability((b.fingerprint, a.fingerprint), 100)


@pytest.mark.parametrize("use_residual", [False, True])
def test_validation_test_boundary(case: Case, use_residual: bool) -> None:
    pair = case.engine.fit_target_models(case.fixture.projection.fingerprint, 40, use_residual)
    evaluation = case.engine.evaluate(
        case.fixture.residual_ids(Partition.TEST),
        100,
        100,
        pair.fingerprint,
        True,
        "fixed-TEST",
    )
    assert evaluation.partition is Partition.TEST and evaluation.test_evaluation_id is not None
    assert len(evaluation.truths) == len(case.fixture.partition(Partition.TEST))
    assert len(evaluation.incremental_metrics) == 5
    with pytest.raises(ContractError):
        case.engine.evaluate(case.fixture.residual_ids(Partition.TEST), 100, 100)
    with pytest.raises(ContractError):
        case.engine.fit(
            case.fixture.spec,
            tuple(r.fingerprint for r in case.fixture.partition(Partition.TEST)),
            100,
        )
    with pytest.raises(ContractError):
        case.engine.evaluate(tuple(v.fingerprint for v in case.fixture.residuals), 100, 100)
    assert (
        next(m for m in evaluation.projection_metrics if m.name is MetricName.MSE).value
        is not None
    )


def test_explicit_feature_export(case: Case) -> None:
    from afre.features import ValueType
    from afre.orthogonalization.cross_sectional import residual_signal
    from afre.orthogonalization.integration import residual_vintage

    value = case.fixture.residuals[0]
    sample = case.repo.get(ResearchSample, value.sample_id)
    template = case.repo.get(FeatureVintage, sample.feature_vintage_ids[0]).feature
    source = residual_signal(case.repo, value).source
    definition = replace(
        template,
        definition=replace(
            template.definition,
            name="derived.orthogonal_candidate",
            version=value.projection_id,
            unit=value.unit,
            value_type=ValueType.NUMBER,
            transformation_version=value.projection_id,
        ),
        source_dataset_ids=(source.dataset_id,),
    )
    vintage = residual_vintage(case.repo, value.fingerprint, definition)
    with case.repo.transaction():
        case.repo.put(definition)
        case.repo.put(source)
        case.repo.put(vintage)
    assert (
        vintage.value == value.residual
        and vintage.clocks.final_available_ns == value.available_ns
    )
    assert case.repo.get(FeatureVintage, vintage.fingerprint) == vintage
    with pytest.raises(ContractError):
        residual_vintage(case.repo, value.fingerprint, template)


def test_actual_hour_day_isolation(case: Case) -> None:
    from examples.regime_horizon_fixture import DAY, HOUR
    from examples.uncertainty_horizon_fixture import horizon_uncertainties

    collections = horizon_uncertainties(case.repo)
    results = []
    for group in collections:
        d = group[0]
        source = source_for(case.repo, d.forecast_id)
        spec, rows = build_rows(
            case.repo,
            source.fold_id,
            source.target,
            40 * DAY,
            tag="actual-" + source.target.horizon.fingerprint,
        )
        model = case.engine.fit(
            spec, tuple(r.fingerprint for r in rows if r.partition is Partition.TRAIN), 40 * DAY
        )
        values = tuple(
            case.engine.residual(model.fingerprint, r.fingerprint, r.origin.timestamp_ns)
            for r in rows
            if r.partition is Partition.VALIDATION
        )
        evaluation = case.engine.evaluate(
            tuple(v.fingerprint for v in values), 100 * DAY, 100 * DAY, target_diagnostics=True
        )
        assert spec.target.horizon.duration_ns in (HOUR, DAY)
        results.append((spec, model, evaluation))
    assert results[0][0].target != results[1][0].target
    assert results[0][1].fingerprint != results[1][1].fingerprint
    with pytest.raises(ContractError):
        case.engine.evaluate(
            (*results[0][2].residual_ids, *results[1][2].residual_ids), 100 * DAY, 100 * DAY
        )


def test_complete_demo(case: Case) -> None:
    from examples.orthogonalization_demo import demonstrate

    assert len(demonstrate(case.repo, case.fixture)) == 37


@pytest.mark.parametrize("family", ["event", "soft-regime", "mixture", "sequence", "nonlinear"])
def test_native_source_unified_audit(case: Case, family: str) -> None:
    identity = case.fixture.upstream.ids(family)[0]
    src = source_for(case.repo, identity)
    ref = reference_for(case.repo, identity, src.sample_id, "audit-" + family)
    value = case.engine.bind(ref, identity, src.sample_id)
    audit = case.engine.audit_lineage(value.fingerprint)
    assert identity in audit.node_ids and src.model_id in audit.node_ids
    assert any(i.startswith("afre.m_fit") for i in audit.node_ids)


def test_regime_probability_and_event_shift(case: Case) -> None:
    from afre.event_conditioned.artifacts import EventConditionedForecast
    from afre.regime_conditioned.artifacts import RegimeConditionedForecast

    # The deliberately late snapshot has no membership; hash order is not eligibility.
    identity = next(
        i
        for i in case.fixture.upstream.ids("soft-regime")
        if case.repo.get(RegimeConditionedForecast, i).membership is not None
    )
    raw = case.repo.get(RegimeConditionedForecast, identity)
    src = source_for(case.repo, identity)
    assert raw.membership is not None
    state = raw.membership.states[0]
    ref = reference_for(case.repo, identity, src.sample_id, "regime-probability", state)
    obs = case.engine.bind(ref, identity, src.sample_id)
    assert obs.value == raw.membership.weights[0] and ref.unit == "probability"
    event_id = case.fixture.upstream.ids("event")[0]
    event = case.repo.get(EventConditionedForecast, event_id)
    src = source_for(case.repo, event_id)
    ref = reference_for(case.repo, event_id, src.sample_id, "event-shift", "shift")
    assert case.engine.bind(ref, event_id, src.sample_id).value == event.shift
    with pytest.raises(ContractError):
        reference_for(case.repo, event_id, src.sample_id, "unsupported", "arbitrary-selector")


def test_uncertainty_policy_and_producer_are_identity_bearing(case: Case) -> None:
    from afre.uncertainty import UncertaintyEngine, UncertaintySpec

    gaussian = case.repo.get(
        ForecastUncertaintyDecomposition, case.fixture.upstream.results("gaussian")[0]
    )
    spec = case.repo.get(UncertaintySpec, gaussian.spec_id)
    ref = reference_for(
        case.repo,
        gaussian.fingerprint,
        gaussian.sample_id,
        "policy-diagnostic",
        "total_predictive",
    )
    revised = UncertaintyEngine(case.repo).decompose(
        replace(spec, interval_levels=(0.05, 0.95)), gaussian.computed_ns
    )
    with pytest.raises(ContractError, match="semantic"):
        case.engine.bind(ref, revised.fingerprint, revised.sample_id)
    changed_ref = reference_for(
        case.repo,
        revised.fingerprint,
        revised.sample_id,
        "policy-diagnostic",
        "total_predictive",
    )
    assert changed_ref.fingerprint != ref.fingerprint
    empirical = next(
        case.repo.get(ForecastUncertaintyDecomposition, i)
        for i in case.fixture.upstream.results("empirical")
        if case.repo.get(ForecastUncertaintyDecomposition, i).sample_id == gaussian.sample_id
    )
    with pytest.raises(ContractError, match="semantic"):
        case.engine.bind(ref, empirical.fingerprint, empirical.sample_id)


def test_diagnostic_producer_keys(case: Case) -> None:
    from afre.orthogonalization.source_policy import producer_key

    for name in (
        "point",
        "gaussian",
        "empirical",
        "calibrated",
        "event",
        "hard-regime",
        "mixture",
        "nonlinear",
        "sequence",
    ):
        assert producer_key(case.repo, case.fixture.upstream.ids(name)[0])
    with pytest.raises(ContractError):
        producer_key(case.repo, case.fixture.spec.target.fingerprint)
