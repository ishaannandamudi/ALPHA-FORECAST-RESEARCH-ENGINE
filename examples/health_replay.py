"""Fresh interpreter replay of canonical health evidence under reversed insertion."""


def replay(source: str, dest: str, reverse: str) -> str:
    import shutil

    from afre.health import HealthDiagnostic as D
    from afre.health import (
        HealthDiagnosticRequest,
        HealthDirection,
        HealthEngine,
        HealthObservation,
        HealthRepository,
        HealthRule,
        HealthSpec,
        HealthStatistic,
        MonitoredArtifactReference,
        MonitoringWindow,
    )
    from afre.serialization import canonical_json

    shutil.copyfile(source, dest)
    with HealthRepository(dest) as r:
        e = HealthEngine(r)
        ids = tuple(
            x[0]
            for x in r._connection.execute(
                "SELECT fingerprint FROM hlt_artifacts "
                "WHERE type_name='HealthObservation' ORDER BY fingerprint"
            )
        )
        obs = tuple(r.get(HealthObservation, i) for i in ids)
        # Exact point observations from a single frozen producer.
        rows = tuple(
            o
            for o in obs
            if "fusion:AVAILABLE" in o.quality
            and dict(o.values).get("predictive_variance") is None
        )
        ref = r.get(MonitoredArtifactReference, rows[0].reference_id)
        req = tuple(
            HealthDiagnosticRequest(k, "prediction", 2)
            for k in (D.PREDICTION_MEAN, D.PREDICTION_KS, D.PREDICTION_STD)
        )
        rules = tuple(
            HealthRule(
                k.value, k, HealthDirection.HIGHER_WORSE, HealthStatistic.DELTA, 2, 0.5, 2.0, 0
            )
            for k in (D.PREDICTION_MEAN, D.PREDICTION_KS, D.PREDICTION_STD)
        )
        windows: tuple[MonitoringWindow, ...] = (
            MonitoringWindow("ref", 10, 11, 120, 2),
            MonitoringWindow("cur", 40, 41, 120, 2),
        )
        if reverse == "1":
            req = tuple(reversed(req))
            rules = tuple(reversed(rules))
            rows = tuple(reversed(rows))
            windows = tuple(reversed(windows))
        for w in windows:
            e._publish((w,))
        wa, wb = sorted(windows, key=lambda w: w.start_ns)
        by = {q.kind: q for q in rules}
        spec = HealthSpec(
            "seed-replay",
            ref.fingerprint,
            ref.target_id,
            ref.horizon_id,
            wa,
            wb,
            req,
            tuple((q.fingerprint, by[q.kind].fingerprint) for q in req),
            tuple(o.fingerprint for o in rows if o.valid_ns == 10),
            tuple(o.fingerprint for o in rows if o.valid_ns == 40),
            2,
            0,
        )
        e.declare(spec, rules)
        out = e.evaluate(spec.fingerprint, 120)
        metrics = tuple(r.get_any(i) for i in out.metric_ids)
        if reverse == "1":
            e._publish(tuple(reversed(metrics)))
        wire = canonical_json(out)
    with HealthRepository(dest) as r:
        assert canonical_json(r.resolve(type(out), out.fingerprint)) == wire
    return wire


if __name__ == "__main__":
    import sys

    print(replay(*sys.argv[1:]))
