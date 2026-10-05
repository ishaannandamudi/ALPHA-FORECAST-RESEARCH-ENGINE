"""Gate training, probability, diagnostics, drift and calibration preserve bounded ancestry."""

import pytest

from afre.calibration.artifacts import CalibrationState
from afre.mixture import MixtureForecast
from afre.schema import ContractError
from afre.serialization import canonical_json
from tests.mixture.conftest import Case


def test_all_supported_root_families_and_semantic_audit(case: Case) -> None:
    evaluation = case.engine.evaluate(case.fixture.forecast_ids, 100, 100)
    test = case.engine.evaluate(case.fixture.test_ids, 100, 100, "mixture-lineage-TEST")
    diagnostic = case.engine.diagnostics(evaluation.fingerprint)
    current = case.engine.diagnostics(test.fingerprint)
    drift = case.engine.drift(diagnostic.fingerprint, current.fingerprint, 100)
    assessment = case.engine.assess_calibration(
        case.forecast.fingerprint, case.fixture.forecast_ids, 100
    )
    probability = case.repo.get(MixtureForecast, case.fixture.probability_ids[0])
    learned = case.repo.get(MixtureForecast, case.fixture.learned_ids[0])
    roots = (case.fixture.learned, probability, learned, diagnostic, drift, assessment)
    for root in roots:
        audit = case.engine.audit_lineage(root.fingerprint)
        assert root.fingerprint in audit.evidence_ids
        assert "target-free-application" in audit.checks
        with pytest.raises(ContractError):
            case.engine.audit_lineage(audit.fingerprint)
    assert case.repo.audit() > 100
    with pytest.raises(ContractError):
        case.engine.audit_lineage(case.sample.fingerprint)


def test_component_calibration_does_not_transfer(case: Case) -> None:
    from afre.mixture.schema import MixtureCalibrationStatus

    identity = case.repo._connection.execute(
        "SELECT fingerprint FROM c_artifacts WHERE type_name='CalibrationState' LIMIT 1"
    ).fetchone()[0]
    state = case.repo.get(CalibrationState, identity)
    before = canonical_json(state)
    assessment = case.engine.assess_calibration(
        case.forecast.fingerprint, case.fixture.forecast_ids, 100, component_state_id=identity
    )
    assert assessment.status is MixtureCalibrationStatus.INCOMPATIBLE
    audit = case.engine.audit_lineage(assessment.fingerprint)
    assert identity in audit.evidence_ids
    assert canonical_json(case.repo.get(CalibrationState, identity)) == before
