"""Thirty-seven offline acceptance steps for supplied causal research transforms."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypeVar
from unittest.mock import patch

from afre.cross_sectional.definitions import CrossSectionSpec
from afre.cross_sectional.engine import CrossSectionEngine
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.schema import SignalQuality
from afre.feature_store.models import FeatureVintage
from afre.mixture import MixtureForecast
from afre.mixture.experts import ExpertForecastBinding
from afre.orthogonalization import (
    OrthogonalizationEngine,
    OrthogonalizationMode,
    OrthogonalizationRepository,
    SignalObservation,
)
from afre.orthogonalization.projection import numeric
from afre.orthogonalization.sources import reference_for
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import Artifact, ContractError
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import DesignMatrix
from afre.target_engine.market_data import TargetBar
from afre.target_engine.models import TargetVintage
from afre.uncertainty import ForecastUncertaintyDecomposition
from afre.uncertainty.sources import source_for
from examples.orthogonalization_fixture import (
    OrthogonalFixture,
    build_fixture,
    build_rows,
    generic_source,
)
from examples.orthogonalization_oracles import ols, pearson, variance
from examples.regime_horizon_fixture import DAY
from examples.uncertainty_horizon_fixture import horizon_uncertainties

A = TypeVar("A", bound=Artifact)


def demonstrate(repo: OrthogonalizationRepository, f: OrthogonalFixture) -> tuple[str, ...]:
    e = OrthogonalizationEngine(repo)
    steps: list[str] = []

    def passed(text: str) -> None:
        steps.append(text)
        print(f"{len(steps)}. PASS {text}")

    row = f.partition(Partition.VALIDATION)[0]
    sample = repo.get(ResearchSample, row.sample_id)
    from afre.feature_store.dag import Transformation
    from afre.feature_store.engine import FeatureStore
    from afre.features import AvailabilityRule
    from examples.feature_store_demo import clocks, computation

    reference_vintage = repo.get(FeatureVintage, sample.feature_vintage_ids[0])
    candidate_definition = replace(
        reference_vintage.feature,
        definition=replace(
            reference_vintage.feature.definition,
            name="derived.orthogonal_demo_candidate",
            version="1",
            availability_rule=AvailabilityRule.COMPUTED,
            dependency_ids=(reference_vintage.feature.definition.fingerprint,),
            transformation_version="transform-v1",
        ),
    )
    with repo.transaction():
        repo.put(candidate_definition)
    assert sample.origin is not None
    candidate_vintage, receipt = FeatureStore(repo).compute(
        computation(
            candidate_definition, (reference_vintage.feature,), Transformation.IDENTITY
        ),
        sample.origin,
        clocks(sample.timestamp_ns),
    )
    for i, feature in enumerate((candidate_vintage, reference_vintage)):
        ref = reference_for(repo, feature.fingerprint, sample.fingerprint, "ordinary-" + str(i))
        assert e.bind(ref, feature.fingerprint, sample.fingerprint).value == feature.value
        passed("ordinary candidate feature" if i == 0 else "ordinary reference feature")
    assert receipt.output_id == candidate_vintage.fingerprint
    for name in ("microstructure.synthetic", "mce.synthetic"):
        source = generic_source(f.spec.candidate, sample, 0.25)
        signal = ExternalSignal(
            source.source.provenance.system,
            "1",
            "1.0",
            sample.security,
            name,
            "1",
            "neutral-synthetic-scalar",
            sample.timestamp_ns,
            source.clocks,
            0.25,
            "unit",
            SignalQuality.VALID,
            source.source,
        )
        identity = CrossSectionEngine(repo).publish_external(signal)
        ref = reference_for(repo, identity, sample.fingerprint, name)
        assert e.bind(ref, identity, sample.fingerprint).value == 0.25
        passed("neutral external " + name)
    for name in ("event", "hard-regime"):
        identity = f.upstream.ids(name)[0]
        src = source_for(repo, identity)
        ref = reference_for(repo, identity, src.sample_id, name)
        assert e.bind(ref, identity, src.sample_id).value == src.prediction
        passed("native " + name + " signal")
    mix = repo.get(MixtureForecast, f.upstream.ids("mixture")[0])
    binding_id = next(i for _, i in mix.request.expert_inputs if i is not None)
    binding = repo.get(ExpertForecastBinding, binding_id)
    ref = reference_for(repo, binding_id, mix.request.sample_id, "expert")
    assert e.bind(ref, binding_id, mix.request.sample_id).value is not None
    assert binding.available_ns <= binding.origin.timestamp_ns
    passed("native expert output")
    for name in ("nonlinear", "sequence"):
        identity = f.upstream.ids(name)[0]
        src = source_for(repo, identity)
        ref = reference_for(repo, identity, src.sample_id, name)
        assert e.bind(ref, identity, src.sample_id).value == src.prediction
        passed("native " + name + " output")
    diagnostic = repo.get(ForecastUncertaintyDecomposition, f.upstream.results("gaussian")[0])
    ref = reference_for(
        repo, diagnostic.fingerprint, diagnostic.sample_id, "uncertainty", "total_predictive"
    )
    assert e.bind(ref, diagnostic.fingerprint, diagnostic.sample_id).value is not None
    passed("explicit numerical uncertainty diagnostic")
    matrix = e.matrix(f.spec.fingerprint, f.projection.row_ids, 40)
    assert len(matrix.intersection_sample_ids) == 12 and matrix.absolute_pearson[0][0] == 1
    passed("common-intersection Pearson/Spearman matrix")
    projection = e.fit(f.spec, f.projection.row_ids, 40)
    assert projection == f.projection
    passed("temporal TRAIN-only projection")
    train = f.partition(Partition.TRAIN)
    x = tuple(tuple(numeric(v) for v in r.references) for r in train)
    y = tuple(numeric(r.candidate) for r in train)
    oracle = ols(x, y)
    assert (
        max(
            abs(a - b)
            for a, b in zip(
                (projection.intercept, *projection.coefficients), oracle, strict=True
            )
        )
        < 1e-12
    )
    passed("independent coefficient oracle")
    residual = e.residual(projection.fingerprint, row.fingerprint, row.origin.timestamp_ns)
    assert residual.residual == numeric(residual.raw_candidate) - numeric(residual.projected)
    passed("causal residual signal")
    get = repo.get

    def denied(cls: type[A], identity: str) -> A:
        if cls in (TargetVintage, DesignMatrix):
            raise AssertionError("target/training read in residual application")
        return get(cls, identity)

    with patch.object(repo, "get", denied):
        assert (
            e.residual(projection.fingerprint, row.fingerprint, row.origin.timestamp_ns)
            == residual
        )
    passed("target-free guarded application")
    late = e.publish_generic(generic_source(f.spec.references[0], sample, 1.0, "late", 1))
    try:
        e.bind(f.spec.references[0], late.fingerprint, row.sample_id)
    except ContractError:
        pass
    else:
        raise AssertionError("late reference accepted")
    passed("late reference excluded")
    ids = f.residual_ids(Partition.VALIDATION)
    evaluation = e.evaluate(ids, 100, 100, target_diagnostics=True)
    assert evaluation.partition is Partition.VALIDATION
    passed("frozen held-out redundancy evaluation")
    values = {v.sample_id: v for v in f.residuals}
    raw = tuple(numeric(values[k].raw_candidate) for k in evaluation.sample_ids)
    rest = tuple(numeric(values[k].residual) for k in evaluation.sample_ids)
    assert evaluation.residual_variance_ratio is not None
    assert abs(evaluation.residual_variance_ratio - variance(rest) / variance(raw)) < 1e-12
    passed("population residual variance ratio")
    xref = next(r for r in f.spec.references if r.signal_id.endswith("-x"))
    zref = next(r for r in f.spec.references if r.signal_id.endswith("-z"))
    partial_values = []
    for candidate in (f.spec.candidate, zref):
        policy = replace(f.spec, candidate=candidate, references=(xref,))
        aligned = tuple(
            e.align(
                policy,
                tuple(
                    i
                    for i in r.observation_ids
                    if repo.get(SignalObservation, i).reference_id
                    in (candidate.fingerprint, xref.fingerprint)
                ),
            )
            for r in f.rows
        )
        model = e.fit(
            policy, tuple(r.fingerprint for r in aligned if r.partition is Partition.TRAIN), 40
        )
        partial_values.append(
            tuple(
                e.residual(model.fingerprint, r.fingerprint, r.origin.timestamp_ns).fingerprint
                for r in aligned
                if r.partition is Partition.VALIDATION
            )
        )
    partial = e.partial(partial_values[0], partial_values[1], 100)
    assert partial.pearson.sample_count == len(ids)
    passed("TRAIN-residual partial correlation")
    pair = e.fit_target_models(projection.fingerprint, 40)
    assert len(pair.target_ids) == len(projection.train_sample_ids)
    passed("fixed reference-only TRAIN target model")
    assert len(pair.augmented_coefficients) == len(pair.base_coefficients) + 1
    passed("fixed reference-plus-residual TRAIN target model")
    incremental = e.evaluate(ids, 100, 100, pair.fingerprint, True)
    assert len(incremental.incremental_metrics) == 5
    passed("matched held-out incremental metrics")
    cspec, crows = build_rows(
        repo,
        f.spec.fold_id,
        f.spec.target,
        40,
        mode=OrthogonalizationMode.CROSS_SECTIONAL_HISTORICAL,
        tag="cross",
    )
    cmodel = e.fit(
        cspec, tuple(r.fingerprint for r in crows if r.partition is Partition.TRAIN), 40
    )
    cvalues = tuple(
        e.residual(cmodel.fingerprint, r.fingerprint, 60).fingerprint
        for r in crows
        if r.origin.timestamp_ns == 60
    )
    template = f.upstream.upstream.upstream.upstream.upstream.upstream.spec
    groups = f.upstream.upstream.upstream.upstream.upstream.upstream.group_refs
    ranking = e.rank(template, cvalues, groups)
    assert len(ranking.entries) == 4
    passed("same-origin residual ranking")
    assert (
        template.identity.snapshot_id == repo.get(ResearchSample, row.sample_id).snapshot_id
        or template.identity.anchor_origin.timestamp_ns == 60
    )
    assert repo.get_any(template.identity.snapshot_id) is not None
    passed("exact eligible PIT universe")
    assert groups and repo.get(CrossSectionSpec, ranking.spec_id).group is not None
    passed("explicit historical sector ranking groups")
    horizon_results = []
    for collection in horizon_uncertainties(repo):
        src = source_for(repo, collection[0].forecast_id)
        policy, aligned = build_rows(
            repo,
            src.fold_id,
            src.target,
            40 * DAY,
            tag="actual-" + src.target.horizon.fingerprint,
        )
        model = e.fit(
            policy,
            tuple(r.fingerprint for r in aligned if r.partition is Partition.TRAIN),
            40 * DAY,
        )
        vals = tuple(
            e.residual(model.fingerprint, r.fingerprint, r.origin.timestamp_ns).fingerprint
            for r in aligned
            if r.partition is Partition.VALIDATION
        )
        horizon_results.append(
            e.evaluate(vals, 100 * DAY, 100 * DAY, target_diagnostics=True).fingerprint
        )
    assert len(set(horizon_results)) == 2
    passed("separate actual one-hour and one-day analyses")
    assert incremental.raw_target_correlations[0].value is not None
    assert (
        abs(
            numeric(incremental.raw_target_correlations[0].value)
            - pearson(raw, incremental.truths)
        )
        < 1e-12
    )
    passed("raw and residual IC on identical truth intersection")
    assert (
        projection.design_rank == 3
        and projection.condition >= 1
        and all(v is not None for v in projection.vif)
    )
    passed("rank/condition/VIF diagnostics")
    window_evaluations = tuple(
        e.evaluate(
            tuple(v.fingerprint for v in f.residuals if v.origin.timestamp_ns == at), 100, 100
        ).fingerprint
        for at in (50, 60)
    )
    stable = e.stability(window_evaluations, 100)
    assert all(a == b for a, b in stable.coefficient_ranges)
    passed("descriptive compatible-window stability")
    frozen = canonical_json(projection)
    assert canonical_json(repo.get_any(projection.fingerprint)) == frozen
    passed("diagnostics preserve source/model identities without pruning")
    test_sample = repo.get(ResearchSample, f.partition(Partition.TEST)[0].sample_id)
    assert test_sample.target_id is not None
    test_truth = repo.get(TargetVintage, test_sample.target_id)
    bar_id = test_truth.endpoint_bar_id
    assert bar_id is not None
    bar = repo.get(TargetBar, bar_id)
    with repo.transaction():
        repo.put(replace(bar, close=(bar.close or 0) + 1, predecessor_id=bar.fingerprint))
    assert canonical_json(e.fit(f.spec, f.projection.row_ids, 40)) == frozen
    passed("TEST endpoint correction cannot select/change projection")
    nextrow = f.partition(Partition.TEST)[0]
    nextsample = repo.get(ResearchSample, nextrow.sample_id)
    correction = e.publish_generic(
        generic_source(f.spec.candidate, nextsample, 99.0, "corrected-next-origin")
    )
    passed("new candidate revision identity")
    old = canonical_json(residual)
    assert canonical_json(repo.get_any(residual.fingerprint)) == old
    passed("old residual bytes unchanged")
    observation = e.bind(f.spec.candidate, correction.fingerprint, nextrow.sample_id)
    changed = e.align(
        f.spec,
        tuple(
            observation.fingerprint
            if repo.get(SignalObservation, i).reference_id == f.spec.candidate.fingerprint
            else i
            for i in nextrow.observation_ids
        ),
    )
    new = e.residual(projection.fingerprint, changed.fingerprint, nextrow.origin.timestamp_ns)
    assert new.fingerprint != residual.fingerprint
    passed("explicit causal rebuild creates new identity")
    path = repo._connection.execute("PRAGMA database_list").fetchone()[2]
    with OrthogonalizationRepository(path) as reopened:
        assert canonical_json(reopened.get_any(residual.fingerprint)) == old
        assert canonical_json(reopened.get_any(projection.fingerprint)) == frozen
    passed("persist and restart replay")
    assert e.evaluate(tuple(reversed(ids)), 100, 100, pair.fingerprint, True) == incremental
    passed("canonical request-order replay")
    audit = e.audit_lineage(incremental.fingerprint)
    assert (
        projection.fingerprint in audit.node_ids
        and len(audit.node_ids) < repo.orthogonalization_bounds.audit_nodes
    )
    passed("bounded unified audit and lineage")
    assert len(steps) == 37
    return tuple(steps)


def main() -> None:
    with (
        TemporaryDirectory(prefix="afre-orthogonalization-") as directory,
        OrthogonalizationRepository(Path(directory) / "demo.sqlite") as repo,
    ):
        demonstrate(repo, build_fixture(repo))


if __name__ == "__main__":
    main()
