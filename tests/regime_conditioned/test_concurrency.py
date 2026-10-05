"""Frozen references survive concurrent provider, target and taxonomy corrections."""

from dataclasses import replace

import pytest

from afre.regime_conditioned import RegimeEngine, RegimeRepository
from afre.serialization import canonical_json
from afre.target_engine.market_data import TargetBar
from tests.regime_conditioned.conftest import Case
from tests.regime_conditioned.test_temporal import context


@pytest.mark.parametrize("kind", ["regime", "taxonomy", "target", "all"])
def test_concurrent_correction_cannot_contaminate_origin(case: Case, kind: str) -> None:
    p, sample, s = context(case)
    old = canonical_json(p)
    with RegimeRepository(case.path) as writer:

        def correction() -> None:
            if kind in ("regime", "all"):
                RegimeEngine(writer).publish_snapshot(replace(s, revision="concurrent"))
            if kind in ("taxonomy", "all"):
                RegimeEngine(writer).publish_taxonomy(
                    replace(
                        s.taxonomy,
                        provider=replace(s.taxonomy.provider, taxonomy_version="concurrent"),
                    )
                )
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

        observed = case.engine.observe(
            case.hard.spec, sample.fingerprint, (s.fingerprint,), snapshot_hook=correction
        )
        assert observed.regime_snapshot_id == s.fingerprint
        result = case.engine.forecast(
            case.hard.model.fingerprint,
            observed.fingerprint,
            p.base_forecast_id,
            60,
            p.base_probability_id,
            snapshot_hook=correction,
        )
        assert result == p and canonical_json(case.repo.get_any(p.fingerprint)) == old
    case.repo.audit()


def test_fit_uses_frozen_old_regime_and_taxonomy(case: Case) -> None:
    p, _, s = context(case)
    with RegimeRepository(case.path) as writer:

        def correction() -> None:
            RegimeEngine(writer).publish_snapshot(replace(s, revision="during-fit"))
            RegimeEngine(writer).publish_taxonomy(
                replace(
                    s.taxonomy,
                    provider=replace(s.taxonomy.provider, taxonomy_version="during-fit"),
                )
            )

        fitted = case.engine.fit(
            case.hard.spec, case.hard.training_ids, 40, 40, 40, snapshot_hook=correction
        )
    assert fitted == case.hard.model
