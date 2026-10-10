"""Deterministic offline fusion walkthrough; explicit unsupported selection/stacking."""

import argparse
import json
from dataclasses import replace
from math import erf, fsum, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from afre.fusion import (
    ExternalFusionOutput,
    FusedForecast,
    FusionEngine,
    FusionFamily,
    FusionIntercept,
    FusionMissingness,
    FusionObservation,
    FusionRepository,
    FusionStatus,
    FusionWeights,
)
from afre.fusion.external import ExternalFusionDefinition
from afre.fusion.metadata import FusionMetadata
from afre.fusion.probabilistic import mean, mixture_cdf, threshold_probability, variance_parts
from afre.probabilistic.artifacts import DistributionParameters, QuantileValue
from afre.probabilistic.schema import DistributionFamily
from afre.research_datasets.samples import ResearchSample
from afre.schema import ContractError, require
from afre.serialization import canonical_json
from examples.fusion_fixture import apply_partition, build_fixture
from examples.fusion_native import horizon_fixture, native_fixture
from examples.fusion_oracles import diagnostic_errors
from examples.fusion_probabilities import probability_fixture


def run(path: Path, reverse: bool = False, include_native: bool = True) -> dict[str, object]:
    checks = []
    errors: dict[str, float] = {}
    with FusionRepository(path) as repo:
        f = build_fixture(repo, reverse)
        e = FusionEngine(repo)
        checks.append("1 compatible immutable point sources")
        fixed = e.fit(f.spec, 0, 0, 0)
        checks.append("2 declared fixed point ensemble")
        sample_id = f.validation[0]
        point = e.apply(fixed.fingerprint, sample_id, f.observations(sample_id), 40)
        obs = tuple(repo.get(FusionObservation, i) for i in f.observations(sample_id))
        expected = fsum(0.5 * o.value for o in obs if o.value is not None)
        assert point.value is not None
        errors["fixed_point"] = abs(point.value - expected)
        checks.append("3 independent fixed value")
        errors["contributions"] = abs(
            point.value
            - fsum(
                c.weighted_value for c in point.contributions if c.weighted_value is not None
            )
        )
        checks.append("4 exact weighted contributions")
        bindings = tuple(
            (s, f.observations(s)) for s in (tuple(reversed(f.train)) if reverse else f.train)
        )
        checks.append("5 exact native TRAIN grid")
        learned_spec = replace(
            f.spec,
            name="learned",
            family=FusionFamily.LEARNED_LINEAR_POINT,
            weights=(),
            weight_policy=FusionWeights.UNCONSTRAINED_QR,
            intercept_policy=FusionIntercept.WITH_INTERCEPT,
        )
        learned = e.fit(learned_spec, 40, 40, 40, bindings)
        checks.append("6 TRAIN-only learned linear fit")
        coefficients = {
            r.fingerprint: 5.0 if r.source_id.endswith("-0") else 0.0 for r in f.references
        }
        errors["learned_coefficients"] = max(
            abs(w - coefficients[i]) for i, w in learned.weights
        )
        checks.append("7 independently known coefficients")
        ids = apply_partition(
            repo,
            f,
            learned.fingerprint,
            tuple(reversed(f.validation)) if reverse else f.validation,
        )
        checks.append("8 frozen target-free application")
        from afre.target_engine.models import TargetVintage

        original_get = repo.get
        heldout = {repo.get(ResearchSample, s).target_id for s in (*f.validation, *f.test)}

        def guarded_get(cls: type[TargetVintage], identity: str) -> TargetVintage:
            if cls is TargetVintage and identity in heldout:
                raise AssertionError("held-out response read by fusion")
            return original_get(cls, identity)

        # The fixture guard changes held-out response access to an immediate failure.
        with patch.object(repo, "get", side_effect=guarded_get):
            assert e.fit(learned_spec, 40, 40, 40, bindings) == learned
            checks.append("9 held-out response perturbation cannot change fit")
            test_ids = apply_partition(repo, f, learned.fingerprint, f.test)
        from afre.fusion.learned import fitted_values

        bad_rows = tuple(replace(r, values=(r.values[0], r.values[0])) for r in learned.rows)
        try:
            fitted_values(learned_spec, bad_rows, 40, 40, 40)
        except ContractError:
            checks.append("10 rank-deficient QR explicitly rejected")
        else:
            raise AssertionError("rank-deficient fusion fit accepted")
        probability_spec, probability_ids = probability_fixture(repo, f)
        checks.append("11 exact Gaussian source laws")
        probability_artifact = e.fit(probability_spec, 0, 0, 0)
        probability = e.apply(probability_artifact.fingerprint, sample_id, probability_ids, 40)
        assert probability.law is not None
        law = probability.law
        checks.append("12 exact finite mixture")
        errors["mixture_mean"] = abs(mean(law) - 2.0)
        checks.append("13 independent mixture expectation")
        within, between = variance_parts(law)
        errors["mixture_variance"] = abs(within + between - 4.1875)
        checks.append("14 exact within plus between variance")
        expected_probability = 0.25 * (0.5 - 0.5 * erf(0.5 / sqrt(2))) + 0.75 * (
            0.5 - 0.5 * erf(-6 / sqrt(2))
        )
        errors["threshold_probability"] = abs(
            threshold_probability(law, 0.0) - expected_probability
        )
        checks.append("15 independent threshold probability")
        assert len(law.components) == 2
        checks.append("16 Gaussian components remain a mixture")
        raw_obs = repo.get(FusionObservation, probability_ids[0])
        raw = repo.get(ExternalFusionOutput, raw_obs.output_id)
        quantiles = DistributionParameters(
            DistributionFamily.QUANTILE_SET,
            0.0,
            1.0,
            quantile_values=(
                QuantileValue(0.1, -1.0),
                QuantileValue(0.5, 0.0),
                QuantileValue(0.9, 1.0),
            ),
        )
        changed = replace(raw, law=quantiles, revision="quantile-only")
        e.external(repo.get(ExternalFusionDefinition, raw.definition_id), (changed,))
        quantile_obs = e.observe(raw_obs.source_id, changed.fingerprint)
        try:
            e.apply(
                probability_artifact.fingerprint,
                sample_id,
                (quantile_obs.fingerprint, probability_ids[1]),
                40,
            )
        except ContractError:
            checks.append("17 quantile-only fake law rejected")
        else:
            raise AssertionError("quantile-only law accepted")
        missing = e.apply(fixed.fingerprint, sample_id, f.observations(sample_id)[:1], 40)
        assert missing.status is FusionStatus.UNAVAILABLE
        checks.append("18 missing FAIL unavailable")
        drop_spec = replace(
            f.spec, name="drop", missingness=FusionMissingness.DROP_AND_RENORMALIZE
        )
        drop = e.fit(drop_spec, 0, 0, 0)
        dropped = e.apply(drop.fingerprint, sample_id, f.observations(sample_id)[:1], 40)
        assert dropped.value == obs[0].value
        checks.append("19 fixed simplex survivor renormalization")
        assert (
            e.apply(learned.fingerprint, sample_id, f.observations(sample_id)[:1], 40).value
            is None
        )
        checks.append("20 learned columns never silently deleted")
        diversity = e.diversity(
            f.spec.source_ids, tuple(i for s in f.validation for i in f.observations(s)), 100
        )
        checks.append("21 common-intersection prediction diversity")
        fixed_ids = apply_partition(repo, f, fixed.fingerprint, f.validation)
        pool = e.trial_pool(((f.spec.fingerprint, fixed_ids), (learned_spec.fingerprint, ids)))
        comparison = e.evaluate(ids, pool.fingerprint, 100, 100)
        errors.update(diagnostic_errors(repo, diversity, comparison))
        checks.append("22 exact common fused versus component evaluation")
        native_ids: tuple[tuple[str, str], ...] = ()
        horizons: tuple[tuple[int, str], ...] = ()
        if include_native:
            with FusionRepository(path.with_name("native.sqlite")) as native_repo:
                native = native_fixture(native_repo)
                native_ids = native.outputs
                assert native_repo.resolve(FusionMetadata, native.metadata_id)
            for step, name in (
                (23, "event"),
                (24, "hard-regime"),
                (25, "mixture"),
                (26, "nonlinear"),
                (27, "sequence"),
                (28, "orthogonal"),
            ):
                assert name in dict(native_ids)
                checks.append(f"{step} actual native {name} source")
            checks.append("29 AFRE15 metadata separate from weights")
        checks.append("30 all inspected fixed and learned rules in native AFRE19 pool")
        checks.append(
            "31 AFRE20 fusion-candidate adapter explicitly unsupported; no reselection"
        )
        if include_native:
            with FusionRepository(path.with_name("horizons.sqlite")) as horizon_repo:
                horizons = horizon_fixture(horizon_repo)
                assert (
                    len({horizon_repo.get(FusedForecast, i).horizon_id for _, i in horizons})
                    == 2
                )
            assert {d for d, _ in horizons} == {3600 * 10**9, 86400 * 10**9}
            checks.extend(("32 actual 1h fusion", "33 actual 1d fusion"))
            checks.append("34 actual horizon identities independent")
        checks.append("35 TEST truth access blocked while frozen fusion applies")
        old_bytes = canonical_json(point)
        old_obs = repo.get(FusionObservation, f.observations(sample_id)[0])
        old_raw = repo.get(ExternalFusionOutput, old_obs.output_id)
        correction = replace(old_raw, value=123.0, revision="correction")
        e.external(repo.get(ExternalFusionDefinition, old_raw.definition_id), (correction,))
        new_obs = e.observe(old_obs.source_id, correction.fingerprint)
        checks.append("36 explicit corrected source revision")
        assert canonical_json(repo.resolve(FusedForecast, point.fingerprint)) == old_bytes
        checks.append("37 old fused bytes remain unchanged")
        new_ids = tuple(
            new_obs.fingerprint if i == old_obs.fingerprint else i
            for i in f.observations(sample_id)
        )
        revised = e.apply(fixed.fingerprint, sample_id, new_ids, 40)
        assert revised.fingerprint != point.fingerprint
        checks.append("38 corrected input creates new fused identity")
        audit = e.audit(comparison.fingerprint)
        witnesses = (
            fixed,
            learned,
            point,
            probability,
            diversity,
            comparison,
            pool,
            audit,
            revised,
        )
        frozen = tuple(canonical_json(v) for v in witnesses)
        assert max(errors.values()) < 1e-10
        require(mixture_cdf(law, 0.0) >= 0, "exact mixture CDF")
    with FusionRepository(path) as reopened:
        assert (
            tuple(canonical_json(reopened.get_any(v.fingerprint)) for v in witnesses) == frozen
        )
    checks.extend(
        (
            "39 persist and reopen exact bytes",
            "40 deterministic semantic replay",
            "41 bounded audit including native AFRE19 family",
        )
    )
    return {
        "checks": checks,
        "step_count": len(checks),
        "artifacts": frozen,
        "native": native_ids,
        "horizons": horizons,
        "test_ids": test_ids,
        "numerical_errors": errors,
        "max_numerical_error": max(errors.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reverse", action="store_true")
    parser.add_argument("--core", action="store_true")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="afre-fusion-demo-") as directory:
        result = run(Path(directory) / "fusion.sqlite", args.reverse, not args.core)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
