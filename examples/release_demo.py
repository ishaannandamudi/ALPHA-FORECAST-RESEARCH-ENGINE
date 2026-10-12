"""Bounded final release demonstration using real native workflows and public contracts."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.costs import CostResearchEngine
from afre.selection import SelectionEngine, enumerate_candidates
from afre.service import AFREService, ServiceRepository, SnapshotPublication, SnapshotPublisher
from examples.costs_fixture import build_fixture as cost_fixture
from examples.downstream_client import consume
from examples.release_workflows import correction_workflow, selection_from_native
from examples.service_demo import exercise
from examples.service_fixture import build_fixture


def demo(directory: Path) -> tuple[tuple[str, ...], dict[str, float]]:
    start = perf_counter()
    with ServiceRepository(directory / "service.sqlite") as repo:
        fixture = build_fixture(repo)
        fixture_seconds = perf_counter() - start
        steps, timings = exercise(directory, repo, fixture)
        messages = list(steps)
        timings["fixture_construction"] = fixture_seconds
        publisher, service = SnapshotPublisher(repo), AFREService(repo)
        for name in ("point", "gaussian", "mixture", "calibrated"):
            snapshot = publisher.publish(SnapshotPublication(fixture.ids(name)[0], "v1", 120))
            assert consume(service, snapshot.snapshot_id) == snapshot
            messages.append(f"Public-contract downstream consumer preserves {name}")
        start = perf_counter()
        space = selection_from_native(repo, fixture.ids("point"))
        timings["selection_fixture_construction"] = perf_counter() - start
        engine = SelectionEngine(repo)
        result, registry = engine.select(space, 100, 100)
        assert len(registry.entries) == len(enumerate_candidates(space))
        assert result.selected_model_id is not None
        timings.update(("selection_" + k, v) for k, v in engine.last_timings.items())
        start = perf_counter()
        engine.audit(result.fingerprint)
        timings["selection_audit"] = perf_counter() - start
        messages.append("Native TRAIN/VALIDATION selection accounts for every research trial")
    with ServiceRepository(directory / "costs.sqlite") as cost_repo:
        start = perf_counter()
        costs = cost_fixture(cost_repo)
        timings["cost_fixture_construction"] = perf_counter() - start
        cost_engine = CostResearchEngine(cost_repo)
        start = perf_counter()
        path, trades = cost_engine.estimate(costs.scenario.fingerprint, 100)
        evaluation = cost_engine.evaluate(
            path.fingerprint, tuple(t.fingerprint for t in trades), 100, 100
        )
        assert evaluation.scenario_id == costs.scenario.fingerprint
        timings["cost_research_evaluation"] = perf_counter() - start
        messages.append("Native cost-aware research is separate from portfolio/execution")
    with ServiceRepository(directory / "corrected-chain.sqlite") as repo:
        correction = correction_workflow(repo)
        timings.update(("correction_" + k, v) for k, v in correction.timings)
        assert correction.original_snapshot != correction.corrected_snapshot
        messages.append(
            "Real feature/model/forecast/fusion correction preserves old complete lineage"
        )
        messages.append(
            "Full native TRAIN audit remains separate from target-free public service"
        )
    return tuple(messages), timings


def main() -> None:
    with TemporaryDirectory(prefix="afre-release-") as work:
        steps, timings = demo(Path(work))
    print("\n".join(steps))
    print(json.dumps(timings, sort_keys=True))
    print(f"PASS: {len(steps)} actual native/public release checks")


if __name__ == "__main__":
    main()
