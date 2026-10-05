"""Fresh hash seeds, reversed insertion and held-out-feature perturbation."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from afre.multihorizon import MultiHorizonEngine, MultiHorizonRepository, SharedParameters
from examples.multihorizon_demo import backbone_spec, build_fixture
from tests.multihorizon.conftest import Case


@pytest.mark.parametrize("seed", ["0", "1", "42", "random"])
def test_fresh_seed_and_reverse(tmp_path: Path, seed: str, case: Case) -> None:
    outputs = []
    for order in ("forward", "reverse"):
        outputs.append(
            subprocess.check_output(
                [
                    sys.executable,
                    "-m",
                    "tests.multihorizon.replay_worker",
                    str(tmp_path / f"{order}.sqlite"),
                    order,
                ],
                env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": "src:."},
                text=True,
            )
        )
    assert outputs[0] == outputs[1]
    from afre.serialization import canonical_json

    f = case.fixture
    shared = case.engine.fit(backbone_spec(f), 55, 55, 55)
    covariance = case.engine.fit_dependence(f.run.fingerprint, 40, 55)
    evaluation = case.engine.evaluate(tuple(b.fingerprint for b in f.bundles), 75, 75)
    audit = case.engine.lineage_audit(f.bundles[0].fingerprint)
    expected = [
        canonical_json(v)
        for v in (f.spec, f.run, shared, covariance, evaluation, audit, *f.bundles)
    ]
    assert json.loads(outputs[0]) == expected


def test_heldout_perturbation_does_not_fit_shared_parameters(
    tmp_path: Path, case: Case
) -> None:
    before = case.engine.fit(backbone_spec(case.fixture), 55, 55, 55)
    with MultiHorizonRepository(tmp_path / "perturbed.sqlite") as repo:
        fixture = build_fixture(repo, heldout_scale=100_000.0)
        after = MultiHorizonEngine(repo).fit(backbone_spec(fixture), 55, 55, 55)
        left = case.repo.get(SharedParameters, before.shared_parameters_id or "")
        right = repo.get(SharedParameters, after.shared_parameters_id or "")
        assert left.coefficients == right.coefficients and left.intercepts == right.intercepts
        assert tuple(r.responses for r in left.sample_rows) == tuple(
            r.responses for r in right.sample_rows
        )
