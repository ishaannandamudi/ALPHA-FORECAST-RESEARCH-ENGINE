"""Independent per-horizon truth/scoring and explicit exact-origin intersections."""

from typing import TYPE_CHECKING, cast

from afre.calibration.artifacts import CalibratedForecast, CalibrationState
from afre.calibration.definitions import CalibrationSpec
from afre.calibration.evaluation import evaluation_for as calibration_evaluation
from afre.multihorizon.artifacts import (
    HorizonEvaluation,
    MultiHorizonEvaluation,
    MultiHorizonFitRun,
    MultiHorizonForecast,
    SharedPointForecast,
)
from afre.multihorizon.definitions import MultiHorizonModelSpec
from afre.probabilistic.definitions import ProbabilisticEvaluationProtocol
from afre.probabilistic.evaluation import evaluate_forecasts as probability_evaluation
from afre.schema import require
from afre.statistical_models.artifacts import PointForecast
from afre.statistical_models.evaluation import evaluate_forecasts, test_record
from afre.statistical_models.linear_algebra import finite, total
from afre.statistical_models.metrics import point_metrics
from afre.statistical_models.schema import MetricName, PredictionScope

if TYPE_CHECKING:
    from afre.multihorizon.repository import MultiHorizonRepository


def evaluation_for(
    repo: "MultiHorizonRepository",
    bundle_ids: tuple[str, ...],
    cutoff_ns: int,
    available_ns: int,
    test_identities: tuple[str | None, ...],
    evidence_only: bool = False,
    pinned: tuple[HorizonEvaluation, ...] = (),
) -> MultiHorizonEvaluation:
    require(
        0 < len(bundle_ids) <= repo.multihorizon_bounds.forecasts
        and len(set(bundle_ids)) == len(bundle_ids),
        "evaluation bundle count/duplicates",
    )
    bundles = tuple(repo.resolve(MultiHorizonForecast, i) for i in sorted(bundle_ids))
    first = bundles[0]
    run = repo.resolve(MultiHorizonFitRun, first.fit_run_id)
    spec = repo.resolve(MultiHorizonModelSpec, run.spec_id)
    require(len(test_identities) == len(spec.bindings), "per-horizon TEST identity shape")
    require(
        all(b.fit_run_id == run.fingerprint and b.available_ns <= cutoff_ns for b in bundles),
        "evaluation mixed fits or unavailable bundles",
    )
    require(
        len({b.origin.fingerprint for b in bundles}) == len(bundles),
        "duplicate evaluation origin",
    )
    rows = []
    truth_maps: list[dict[str, tuple[float, float]]] = []
    for h, binding in enumerate(spec.bindings):
        entries = tuple(
            b.entries[h] for b in bundles if b.entries[h].point_forecast_id is not None
        )
        if not entries:
            require(test_identities[h] is None, "empty horizon cannot record TEST access")
            rows.append(
                HorizonEvaluation(
                    binding.target_definition_id,
                    None,
                    None,
                    None,
                    None,
                    (),
                    (),
                    (),
                    (),
                    len(bundles),
                )
            )
            truth_maps.append({})
            continue
        points = tuple(
            cast(PointForecast | SharedPointForecast, repo.get_any(e.point_forecast_id or ""))
            for e in entries
        )
        require(
            all(isinstance(p, (PointForecast, SharedPointForecast)) for p in points),
            "point layer",
        )
        point_ids = tuple(
            p.scaffold_forecast_id if isinstance(p, SharedPointForecast) else p.fingerprint
            for p in points
        )
        original = tuple(repo.resolve(PointForecast, i) for i in point_ids)
        is_test = original[0].input.scope is PredictionScope.TEST
        require(
            is_test == (test_identities[h] is not None),
            "TEST requires exact horizon access identity",
        )
        seal = None
        if evidence_only:
            from afre.research_datasets.splits import TestEvaluation

            seal = (
                repo.resolve(TestEvaluation, pinned[h].test_evaluation_id or "")
                if is_test
                else None
            )
        elif is_test:
            seal = test_record(
                repo,
                binding.fold_id,
                test_identities[h] or "",
                "multi-horizon-evaluation",
                cutoff_ns,
            )
            repo.put(seal)
        point_eval = evaluate_forecasts(repo, point_ids, cutoff_ns, available_ns, seal)
        mapping = {o.fingerprint: p for o, p in zip(original, points, strict=True)}
        values = {
            repo.resolve(PointForecast, pair.prediction_id).input.origin.fingerprint: (
                mapping[pair.prediction_id].value,
                pair.truth,
            )
            for pair in point_eval.pairs
        }
        metrics = point_metrics(
            tuple(v[0] for v in values.values()), tuple(v[1] for v in values.values())
        )
        raw_eval, cal_eval = None, None
        if binding.probability_model_id is not None:
            protocol = ProbabilisticEvaluationProtocol()
            if binding.calibration_state_id is not None:
                state = repo.resolve(CalibrationState, binding.calibration_state_id)
                cs = repo.resolve(CalibrationSpec, state.inputs.spec_id)
                protocol = ProbabilisticEvaluationProtocol(
                    (cs.interval,) if cs.interval else ()
                )
            raw_eval = probability_evaluation(
                repo,
                tuple(e.probability_forecast_id or "" for e in entries),
                protocol,
                cutoff_ns,
                available_ns,
                seal,
            )
            if not evidence_only:
                for interval in protocol.intervals:
                    repo.put(interval)
                repo.put(protocol)
                repo.put(raw_eval)
            if binding.calibration_state_id is not None:
                for e in entries:
                    repo.resolve(CalibratedForecast, e.calibrated_forecast_id or "")
                cal_eval = calibration_evaluation(
                    repo, tuple(e.calibrated_forecast_id or "" for e in entries), raw_eval
                )
                if not evidence_only:
                    repo.put(cal_eval)
        if not evidence_only:
            repo.put(point_eval)
        rows.append(
            HorizonEvaluation(
                binding.target_definition_id,
                point_eval.fingerprint,
                raw_eval.fingerprint if raw_eval else None,
                cal_eval.fingerprint if cal_eval else None,
                seal.fingerprint if seal else None,
                metrics,
                raw_eval.scores if raw_eval else (),
                cal_eval.calibrated_scores if cal_eval else (),
                tuple(sorted(values)),
                len(bundles) - len(values),
            )
        )
        truth_maps.append(values)
    intersection = tuple(
        sorted(set(truth_maps[0]).intersection(*(set(m) for m in truth_maps[1:])))
    )
    matched = tuple(
        point_metrics(
            tuple(m[k][0] for k in intersection), tuple(m[k][1] for k in intersection)
        )
        for m in truth_maps
    )
    mses = tuple(
        next((m.value for m in row.point_metrics if m.name is MetricName.MSE), None)
        for row in rows
    )
    weighted = None
    if all(v is not None or w == 0 for v, w in zip(mses, spec.horizon_weights, strict=True)):
        weighted = finite(
            total(
                [
                    finite((v or 0.0) * w)
                    for v, w in zip(mses, spec.horizon_weights, strict=True)
                ]
            )
            / total(list(spec.horizon_weights))
        )
    return MultiHorizonEvaluation(
        run.fingerprint,
        bundle_ids,
        tuple(rows),
        spec.horizon_weights,
        weighted,
        intersection,
        matched,
        cutoff_ns,
        available_ns,
    )
