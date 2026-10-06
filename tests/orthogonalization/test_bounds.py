"""Closed numerical/resource policies and explicit bounded request failures."""

from dataclasses import fields, replace

import pytest

from afre.orthogonalization import (
    OrthogonalizationBounds,
    OrthogonalizationEngine,
    OrthogonalizationRepository,
    SignalObservation,
)
from afre.research_datasets.schema import Partition
from afre.schema import ContractError
from tests.orthogonalization.conftest import Case


@pytest.mark.parametrize("field", [f.name for f in fields(OrthogonalizationBounds)])
def test_hard_limits(field: str) -> None:
    b = OrthogonalizationBounds()
    for value in (0, getattr(b, field) + 1):
        with pytest.raises(ContractError):
            replace(b, **{field: value})


@pytest.mark.parametrize(
    "limit",
    [
        "references",
        "rows",
        "cells",
        "serialized_bytes",
        "artifacts",
        "windows",
        "audit_nodes",
        "audit_depth",
        "candidates",
    ],
)
def test_resource_limits(case: Case, limit: str) -> None:
    path = case.repo._connection.execute("PRAGMA database_list").fetchone()[2]
    f = case.fixture
    with OrthogonalizationRepository(
        path, replace(OrthogonalizationBounds(), **{limit: 1})
    ) as r:
        e = OrthogonalizationEngine(r)
        with pytest.raises(ContractError):
            if limit in ("audit_nodes", "audit_depth"):
                e.audit_lineage(f.projection.fingerprint)
            elif limit == "cells":
                e.matrix(
                    f.spec.fingerprint,
                    tuple(x.fingerprint for x in f.partition(Partition.TRAIN)),
                    100,
                )
            elif limit == "windows":
                e.stability((f.projection.fingerprint, f.projection.fingerprint), 100)
            elif limit == "artifacts":
                e.register(replace(f.spec.candidate, signal_id="extra", semantic_name="extra"))
            elif limit == "candidates":
                e.fit_candidates(((f.spec, f.projection.row_ids),) * 2, 40)
            else:
                r.get_any(f.projection.fingerprint if limit == "rows" else f.spec.fingerprint)


@pytest.mark.parametrize(
    "kind",
    [
        "empty",
        "duplicate",
        "same-candidate",
        "few",
        "condition",
        "tolerance",
        "seed",
        "weight",
        "version",
        "target",
        "selector",
        "key",
    ],
)
def test_invalid_policies(case: Case, kind: str) -> None:
    s = case.fixture.spec
    with pytest.raises(ContractError):
        if kind == "empty":
            replace(s, references=())
        elif kind == "duplicate":
            replace(s, references=(s.references[0],) * 2)
        elif kind == "same-candidate":
            replace(s, references=(s.candidate,))
        elif kind == "few":
            replace(s, minimum_samples=2)
        elif kind == "condition":
            replace(s, condition_limit=0.1)
        elif kind == "tolerance":
            replace(s, tolerance=0.0)
        elif kind == "seed":
            replace(s, seed=-1)
        elif kind == "weight":
            replace(s, weighting="heldout-fitted")
        elif kind == "version":
            replace(s, implementation_version="future-solver")
        elif kind == "target":
            replace(
                s, candidate=replace(s.candidate, target=replace(s.target, name="target.other"))
            )
        elif kind == "selector":
            replace(s.candidate, selector="eval(payload)")
        else:
            replace(s.candidate, source_key=())


def test_request_order_and_multi_candidate(case: Case) -> None:
    f = case.fixture
    xref = next(r for r in f.spec.references if r.signal_id.endswith("-x"))
    zref = next(r for r in f.spec.references if r.signal_id.endswith("-z"))
    second = replace(f.spec, candidate=zref, references=(xref,))
    rows = tuple(
        case.engine.align(
            second,
            tuple(
                i
                for i in r.observation_ids
                if case.repo.get(SignalObservation, i).reference_id
                in (xref.fingerprint, zref.fingerprint)
            ),
        )
        for r in f.partition(Partition.TRAIN)
    )
    requests = ((f.spec, f.projection.row_ids), (second, tuple(r.fingerprint for r in rows)))
    assert case.engine.fit_candidates(requests, 40) == case.engine.fit_candidates(
        tuple(reversed(requests)), 40
    )
    assert case.engine.fit_candidates(requests, 40)[0].spec_id in (
        f.spec.fingerprint,
        second.fingerprint,
    )
    with pytest.raises(ContractError):
        case.engine.fit_candidates((), 40)
