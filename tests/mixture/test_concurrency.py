"""Exact pinned identities survive expert, gate and market truth corrections."""

from dataclasses import replace

import pytest

from afre.mixture import (
    ExpertForecastBinding,
    ExternalExpertForecast,
    MixtureEngine,
    MixtureRepository,
)
from afre.serialization import canonical_json
from afre.target_engine.market_data import TargetBar
from tests.mixture.conftest import Case


@pytest.mark.parametrize("kind", ["expert", "gate", "target", "all"])
def test_frozen_application(case: Case, kind: str) -> None:
    request = case.forecast.request
    binding = next(
        case.repo.get(ExpertForecastBinding, b)
        for _, b in request.expert_inputs
        if b
        and case.repo.get(ExpertForecastBinding, b).forecast_id.startswith("afre.mix_external")
    )
    raw = case.repo.get(ExternalExpertForecast, binding.forecast_id)
    before = canonical_json(case.forecast)
    with MixtureRepository(case.path) as writer:

        def correction() -> None:
            engine = MixtureEngine(writer)
            if kind in ("expert", "all"):
                engine.publish_external(
                    replace(raw, revision="concurrent", point=(raw.point or 0.0) + 0.123)
                )
            if kind in ("gate", "all"):
                weights = tuple(
                    (i, 1.0 if index == 0 else 0.0)
                    for index, (i, _) in enumerate(case.fixture.fixed.weights)
                )
                engine.publish_gate(replace(case.fixture.fixed, weights=weights))
            if kind in ("target", "all"):
                identity = writer._connection.execute(
                    "SELECT fingerprint FROM target_artifacts "
                    "WHERE type_name='TargetBar' LIMIT 1"
                ).fetchone()[0]
                bar = writer.get(TargetBar, identity)
                with writer.transaction():
                    writer.put(
                        replace(
                            bar, close=(bar.close or 0.0) + 1.0, predecessor_id=bar.fingerprint
                        )
                    )

        result = case.engine.forecast(request, snapshot_hook=correction)
    assert canonical_json(result) == before
    assert canonical_json(case.repo.get_any(result.fingerprint)) == before


def test_fit_snapshot_survives_new_model_publication(case: Case) -> None:
    with MixtureRepository(case.path) as writer:

        def correction() -> None:
            MixtureEngine(writer).fit(
                case.fixture.learned_spec, case.fixture.training_ids, 41, 41, 41
            )

        result = case.engine.fit(
            case.fixture.learned_spec,
            case.fixture.training_ids,
            40,
            40,
            40,
            snapshot_hook=correction,
        )
    assert result == case.fixture.learned
