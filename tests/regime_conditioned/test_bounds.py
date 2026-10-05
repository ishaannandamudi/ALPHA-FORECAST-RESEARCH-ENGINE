"""Overflow fails atomically instead of truncating state, history or research evidence."""

from dataclasses import replace

import pytest

from afre.regime_conditioned import RegimeConditionedSample, RegimeSnapshot
from afre.regime_conditioned.queries import snapshots_known
from afre.schema import ContractError
from examples.regime_conditioned_demo import snapshot, taxonomy
from tests.regime_conditioned.conftest import Case
from tests.regime_conditioned.test_temporal import context


@pytest.mark.parametrize(
    "bound",
    [
        "states",
        "taxonomies",
        "snapshots",
        "samples",
        "transitions",
        "evaluations",
        "drift_windows",
        "audit_nodes",
        "audit_depth",
        "serialized_bytes",
    ],
)
def test_explicit_overflow(case: Case, bound: str) -> None:
    p, sample, s = context(case)
    engine = case.engine
    if bound == "drift_windows":
        a = engine.evaluate(case.hard.forecast_ids, 100, 100)
        b = engine.evaluate(case.hard.test_ids, 100, 100, "bounded-drift")
        engine.drift(a.fingerprint, b.fingerprint, 100)
    if bound == "transitions":
        ids = tuple(
            engine.publish_snapshot(snapshot(s.taxonomy, sample, at=at, state="A"))
            for at in (58, 59, 60)
        )
    if bound == "evaluations":
        engine.evaluate(case.hard.forecast_ids, 100, 100)
    case.repo.regime_bounds = replace(
        case.repo.regime_bounds, **{bound: 1 if bound != "serialized_bytes" else 20}
    )
    with pytest.raises(ContractError, match="bound"):
        if bound == "states":
            case.repo.get(RegimeSnapshot, s.fingerprint)
        elif bound == "taxonomies":
            engine.publish_taxonomy(
                replace(taxonomy(), provider=replace(taxonomy().provider, taxonomy_version="2"))
            )
        elif bound == "snapshots":
            engine.publish_snapshot(replace(s, revision="new"))
        elif bound == "samples":
            engine.fit(case.hard.spec, case.hard.training_ids, 40, 40, 40)
        elif bound == "transitions":
            engine.observe(case.hard.spec, sample.fingerprint, ids)
        elif bound == "evaluations":
            engine.evaluate(case.hard.forecast_ids, 101, 101)
        elif bound == "drift_windows":
            engine.drift(a.fingerprint, b.fingerprint, 100, minimum_count=3)
        else:
            engine.audit_lineage(p.fingerprint)


def test_indexed_history_bound(case: Case) -> None:
    _, sample, s = context(case)
    for at in (58, 59):
        case.engine.publish_snapshot(snapshot(s.taxonomy, sample, at=at))
    case.repo.regime_bounds = replace(case.repo.regime_bounds, snapshots=1)
    with pytest.raises(ContractError, match="query bound"):
        snapshots_known(
            case.repo, s.taxonomy.provider.provider, s.taxonomy.fingerprint, s.subject, 60
        )


def test_application_rejects_model_unavailability(case: Case) -> None:
    p, _, _ = context(case)
    from afre.regime_conditioned.forecasts import forecast_for

    model = replace(case.hard.model, available_ns=61)
    with pytest.raises(ContractError, match="before inputs"):
        forecast_for(
            case.repo,
            model,
            case.repo.get(RegimeConditionedSample, p.observation_id),
            p.base_forecast_id,
            p.base_probability_id,
            60,
        )
