"""Separate health identities for actual native one-hour and one-day targets."""

from afre.fusion import FusedForecast
from afre.health import (
    HealthDiagnostic,
    HealthDiagnosticRequest,
    HealthDirection,
    HealthEngine,
    HealthRepository,
    HealthRule,
    HealthSpec,
    HealthStatistic,
    ModelHealthSnapshot,
    MonitoringWindow,
)
from examples.fusion_native import horizon_fixture


def horizon_monitors(repo: HealthRepository) -> tuple[tuple[int, ModelHealthSnapshot], ...]:
    results = []
    engine = HealthEngine(repo)
    for duration, identity in horizon_fixture(repo):
        ref = engine.monitor(identity)
        raw = repo.get(FusedForecast, identity)
        at = raw.origin.timestamp_ns
        row = engine.observe(ref.fingerprint, identity, at)
        request = HealthDiagnosticRequest(HealthDiagnostic.PREDICTION_MEAN, "prediction", 1)
        rule = HealthRule(
            "hour-day-rule",
            request.kind,
            HealthDirection.HIGHER_WORSE,
            HealthStatistic.DELTA,
            1,
            1.0,
            2.0,
            ref.available_ns,
        )
        spec = HealthSpec(
            "actual-horizon",
            ref.fingerprint,
            ref.target_id,
            ref.horizon_id,
            MonitoringWindow("ref", at, at + 1, at + 1, 1),
            MonitoringWindow("cur", at, at + 1, at + 1, 1),
            (request,),
            ((request.fingerprint, rule.fingerprint),),
            (row.fingerprint,),
            (row.fingerprint,),
            1,
            ref.available_ns,
            allow_overlap=True,
        )
        engine.declare(spec, (rule,))
        results.append((duration, engine.evaluate(spec.fingerprint, at + 1)))
    return tuple(results)
