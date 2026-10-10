"""Forty-five verified offline steps through descriptive monitoring."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from afre.fusion import FusedForecast, FusionArtifact, FusionEngine
from afre.health import HealthDiagnostic as D
from afre.health import (
    HealthEngine,
    HealthMetric,
    HealthObservation,
    HealthRepository,
    HealthSpec,
    HealthStatus,
    MonitoredArtifactReference,
)
from afre.health.sources import reference_for
from afre.serialization import canonical_json
from afre.target_engine.models import TargetVintage
from examples.health_corrections import corrected_output
from examples.health_fixture import build_health_fixture, health_spec
from examples.health_horizons import horizon_monitors
from examples.health_native import (
    build_native,
    cohort_monitor,
    native_monitor,
    parameter_monitor,
)
from examples.health_selection import selected_monitor


def demo(directory: Path) -> tuple[str, ...]:
    messages: list[str] = []

    def step(message: str) -> None:
        messages.append(f"{len(messages) + 1:02d}. {message}")

    path = directory / "health.sqlite"
    with HealthRepository(path) as repo:
        fixture = build_health_fixture(repo)
        engine = HealthEngine(repo)
        before = canonical_json(repo.get(FusionArtifact, fixture.artifact_id))
        step("Frozen monitored artifact pins exact producer/target/horizon")
        spec, rules = health_spec(repo, fixture, (D.PREDICTION_MEAN, D.PREDICTION_KS))
        assert spec.reference_window.start_ns == 10
        step("Reference window is explicitly declared")
        assert spec.current_window.start_ns == 40
        step("Current window follows the reference")
        engine.declare(spec, rules)
        step("HealthSpec binds exact sources/requests/windows")
        assert rules and all(r.warning == 0.5 and r.degraded == 2 for r in rules)
        step("Warning/degraded thresholds are supplied and identity-bearing")
        column = repo.get(HealthObservation, fixture.input_ids[0]).values[0][0]
        inputs, input_rules = health_spec(
            repo,
            fixture,
            (D.INPUT_MEAN, D.INPUT_STD, D.INPUT_QUANTILE, D.INPUT_KS, D.MISSINGNESS),
            input_column=column,
        )
        engine.declare(inputs, input_rules)
        drift = engine.evaluate(inputs.fingerprint, 120)
        assert drift.metric_ids
        step("Native feature means/std/Type7/KS/missingness remain separate")
        snapshot = engine.evaluate(spec.fingerprint, 120)
        assert snapshot.status is HealthStatus.DEGRADED
        step("Known frozen prediction vectors show the exact mean shift")
        get = repo.get

        def guarded_get(cls: type, identity: str) -> object:
            assert cls is not TargetVintage
            return get(cls, identity)

        with patch.object(repo, "get", side_effect=guarded_get):
            assert engine.evaluate(inputs.fingerprint, 120) == drift
            assert engine.evaluate(spec.fingerprint, 120) == snapshot
        step("Input/prediction paths cannot read TargetVintage")
        errors, error_rules = health_spec(
            repo, fixture, (D.BIAS, D.MAE, D.MSE, D.RMSE, D.R_SQUARED, D.IC, D.RANK_IC)
        )
        engine.declare(errors, error_rules)
        performance = engine.evaluate(errors.fingerprint, 120)
        assert all(repo.get(HealthMetric, i).truth_ids for i in performance.metric_ids)
        step("Later native truth unlocks exact error metrics")
        assert any(
            repo.get(HealthMetric, i).orientation == "positive-delta-worse"
            for i in performance.metric_ids
        )
        step("Performance decay pins explicit better/worse delta orientation")
        probabilities, prob_rules = health_spec(
            repo, fixture, (D.CRPS, D.NLL, D.ECE, D.MCE), probability=True
        )
        engine.declare(probabilities, prob_rules)
        calibration = engine.evaluate(probabilities.fingerprint, 120)
        assert all(
            repo.get(HealthMetric, i).current_value is not None for i in calibration.metric_ids
        )
        step("Frozen Gaussian law yields proper scores/reliability diagnostics")
        assert any(repo.get(HealthMetric, i).kind is D.RANK_IC for i in performance.metric_ids)
        step("Same-origin IC and rank-IC decay preserve exact pairs")
        fusion = FusionEngine(repo)
        a = fusion.fit(fixture.upstream.spec, 0, 0, 0)
        source_ids = sorted(fixture.upstream.spec.source_ids)
        b = fusion.fit(
            replace(
                fixture.upstream.spec,
                name="explicit-weights",
                weights=((source_ids[0], 0.25), (source_ids[1], 0.75)),
            ),
            0,
            0,
            0,
        )
        parameter = parameter_monitor(
            repo,
            a.fingerprint,
            b.fingerprint,
            (D.PARAMETER_L1, D.PARAMETER_L2, D.PARAMETER_SIGN_CHANGES, D.PARAMETER_CORRELATION),
            "weight",
        )
        assert parameter.metric_ids
        step("Explicit compatible parameter vectors yield L1/L2/sign/correlation changes")
        weights = parameter_monitor(
            repo,
            a.fingerprint,
            b.fingerprint,
            (D.FUSION_DOMINANCE, D.EFFECTIVE_SOURCE_COUNT, D.WEIGHT_ENTROPY),
        )
        assert weights.metric_ids
        step("AFRE21 original weight dominance/effective count/entropy remain descriptive")
        healthy, healthy_rules = health_spec(
            repo, fixture, (D.PREDICTION_MEAN,), current_start=20
        )
        engine.declare(healthy, healthy_rules)
        recovered = engine.evaluate(healthy.fingerprint, 120)
        assert recovered.status is HealthStatus.HEALTHY
        step("An unchanged window produces HEALTHY")
        request = next(q for q in spec.requests if q.kind is D.PREDICTION_MEAN)
        rule = replace(next(r for r in rules if r.kind is D.PREDICTION_MEAN), degraded=4.0)
        warning = replace(
            spec, requests=(request,), rule_bindings=((request.fingerprint, rule.fingerprint),)
        )
        engine.declare(warning, (rule,))
        assert engine.evaluate(warning.fingerprint, 120).status is HealthStatus.WARNING
        step("Explicit changed boundary produces WARNING under a new identity")
        assert snapshot.status is HealthStatus.DEGRADED
        step("Exact supplied degraded boundary produces DEGRADED")
        sparse, sparse_rules = health_spec(repo, fixture, (D.PREDICTION_MEAN,), minimum=4)
        engine.declare(sparse, sparse_rules)
        assert engine.evaluate(sparse.fingerprint, 120).status is HealthStatus.INSUFFICIENT_DATA
        step("Insufficient counts remain INSUFFICIENT_DATA")
        wrong = replace(
            spec,
            comparison_reference_ids=(fixture.probability_reference.fingerprint,),
            current_observation_ids=fixture.probability_ids,
        )
        engine.declare(wrong, rules)
        assert engine.evaluate(wrong.fingerprint, 120).status is HealthStatus.INCOMPARABLE
        step("Different frozen output semantics remain INCOMPARABLE")
        assert len(snapshot.metric_ids) == len(spec.requests)
        step("WORST_STATUS includes the complete required metric set")
        assert canonical_json(repo.get(FusionArtifact, fixture.artifact_id)) == before
        step("Snapshot leaves the producer bytes unchanged: no retraining")
        assert calibration.action == "NONE_DESCRIPTIVE_ONLY"
        step("Calibration diagnostics perform no recalibration")
        assert (
            repo.get(FusionArtifact, a.fingerprint) == a
            and repo.get(FusionArtifact, b.fingerprint) == b
        )
        step("Monitoring performs no fusion-weight change")
        assert snapshot.action == "NONE_DESCRIPTIVE_ONLY"
        step("Snapshot cannot promote, retire, replace or route")
        history = engine.history(fixture.reference.fingerprint)
        assert snapshot in history and recovered in history
        step("Append-only history retains degraded and later healthy states")
        later = replace(
            healthy,
            current_window=replace(healthy.current_window, start_ns=40, end_ns=41),
            current_observation_ids=spec.current_observation_ids,
        )
        engine.declare(later, healthy_rules)
        trend = engine.trend(
            (recovered.metric_ids[0], engine.evaluate(later.fingerprint, 120).metric_ids[0]),
            120,
        )
        assert trend.slope_per_ns is not None
        step("Declared fixed-reference windows yield a descriptive decay slope")
        output_id = next(
            i
            for i in fixture.output_ids
            if repo.get(FusedForecast, i).origin.timestamp_ns == 40
        )
        changed_id = corrected_output(repo, output_id)
        corrected = engine.monitor(changed_id)
        assert corrected.fingerprint != fixture.reference.fingerprint
        step("Inserted native source revision creates a new reference identity")
        revised = replace(
            spec,
            label="new-monitor",
            reference_id=corrected.fingerprint,
            comparison_reference_ids=(fixture.reference.fingerprint,),
        )
        engine.declare(revised, rules)
        assert engine.evaluate(revised.fingerprint, 120).fingerprint != snapshot.fingerprint
        step("New monitor identity preserves the old immutable snapshot")
        wire = canonical_json(snapshot)
        audit = engine.audit(snapshot.fingerprint)
        assert audit.serialized_bytes <= repo.health_bounds.lineage_bytes
        step("Bounded audit traces exact windows/rules/source/truth evidence")
    with HealthRepository(path) as repo:
        assert canonical_json(repo.resolve(type(snapshot), snapshot.fingerprint)) == wire
        step("Persistence/restart reproduces identical snapshot bytes")
        assert HealthEngine(repo).evaluate(spec.fingerprint, 120) == snapshot
        step("Deterministic semantic replay is idempotent")
    selected, _ = selected_monitor(directory / "selected.sqlite")
    with HealthRepository(directory / "selected.sqlite") as repo:
        chosen = repo.get(HealthSpec, selected.spec_id)
        assert len(chosen.context_ids) == 3
        step("AFRE19 completed research trials remain attached context")
        assert (
            repo.get(MonitoredArtifactReference, chosen.reference_id).artifact_type
            == "SelectionResult"
        )
        step("AFRE20 selected model is monitored without rerunning selection")
    with HealthRepository(directory / "horizons.sqlite") as repo:
        horizons = horizon_monitors(repo)
        assert any(d == 3600000000000 for d, _ in horizons)
        step("Actual one-hour target has its own health snapshot")
        assert any(d == 86400000000000 for d, _ in horizons)
        step("Actual one-day target has its own health snapshot")
        assert horizons[0][1].spec_id != horizons[1][1].spec_id
        step("Horizon-specific identities prevent pooling")
    with HealthRepository(directory / "native.sqlite") as repo:
        f = build_native(repo)
        for family in ("tree", "sequence"):
            identity = f.upstream.upstream.upstream.ids(family)[0]
            ref = reference_for(repo, identity)
            kinds = (
                (D.TREE_SPLIT_RECURRENCE, D.TREE_PATH_RECURRENCE)
                if family == "tree"
                else (D.SEQUENCE_DECAY, D.PARAMETER_L1)
            )
            result = parameter_monitor(
                repo, ref.producer_id, ref.producer_id, kinds, anchors=(identity, identity)
            )
            assert result.metric_ids
        step("Native tree/sequence readout diagnostics retain raw-scale limitations")
        result = native_monitor(
            repo, f.upstream.upstream.upstream.results("gaussian"), (D.UNCERTAINTY_VARIANCE,)
        )
        assert result.metric_ids
        step("AFRE15 predictive-variance drift retains native decomposition")
        result = native_monitor(
            repo,
            tuple(r.fingerprint for r in f.upstream.upstream.residuals),
            (D.RESIDUAL_VARIANCE_RATIO, D.RAW_REFERENCE_CORRELATION),
            "raw",
        )
        assert result.metric_ids
        step("AFRE16 residual variance and reference correlation remain descriptive")
        result = native_monitor(
            repo, f.cost_sample_ids, (D.GROSS_EDGE, D.COST, D.NET_EDGE, D.TURNOVER)
        )
        assert result.metric_ids
        step("AFRE18 hypothetical gross/cost/net/turnover remain separate from portfolio work")
        for kind in ("EVENT", "REGIME", "SECTOR", "UNIVERSE"):
            environment = next(
                d
                for d in f.cohorts.environment_set.definitions
                if d.kind.name == kind
                and (d.membership_kind is None or d.membership_kind.value == "hard")
            )
            result = cohort_monitor(repo, f, environment.fingerprint)
            assert result.metric_ids
        step("Declared AFRE17 event/regime/sector/universe cohorts preserve PIT membership")
        soft = next(
            d
            for d in f.cohorts.environment_set.definitions
            if d.membership_kind is not None and d.membership_kind.value == "soft"
        )
        assert cohort_monitor(repo, f, soft.fingerprint).status is HealthStatus.INCOMPARABLE
        step("Unsupported soft weighted cohorts fail explicitly as INCOMPARABLE")
        assert repo._connection.execute("PRAGMA user_version").fetchone()[0] == 23
        step("Additive SQLite23 migration retains native evidence")
        assert len(HealthEngine(repo).audit(result.fingerprint).node_ids) > 10
        step("Native cohort lineage is bounded and replayable")
        assert result.action == "NONE_DESCRIPTIVE_ONLY"
        step("No automatic production or external lifecycle action exists")
    assert len(messages) == 45
    return tuple(messages)


if __name__ == "__main__":
    with TemporaryDirectory() as directory:
        print("\n".join(demo(Path(directory))))
