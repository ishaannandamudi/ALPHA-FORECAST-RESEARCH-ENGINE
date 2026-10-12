"""Final static boundary and adversarial public wire/numerical checks."""

import ast
from math import isclose
from pathlib import Path

import pytest

from afre.service import ServiceLawComponent, ServiceProbabilityLaw, deserialize

FORBIDDEN = {
    "socket",
    "urllib",
    "requests",
    "httpx",
    "http",
    "ftplib",
    "subprocess",
    "pickle",
    "joblib",
    "importlib",
    "ame",
    "mce",
    "eie",
    "hft",
    "options_engine",
}


def test_runtime_import_and_execution_boundary() -> None:
    for path in Path("src/afre").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(n.name.split(".")[0].lower() not in FORBIDDEN for n in node.names), (
                    path
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0].lower() not in FORBIDDEN, path
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "__import__"}, path


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":"1.0","artifact":{"$type":"os.system","fields":{"command":"ignored"}}}',
        '{"schema_version":"1.0","artifact":{"$type":"ServiceReply","fields":{}}}',
        '{"schema_version":"1.0","artifact":NaN}',
        '{"schema_version":"1.0","schema_version":"1.0","artifact":null}',
        "[" * 80 + "0" + "]" * 80,
    ],
)
def test_public_decoder_rejects_executable_or_unbounded_shapes(payload: str) -> None:
    with pytest.raises(ValueError):
        deserialize(payload)


def test_tiny_gaussian_tail_independent_oracle() -> None:
    law = ServiceProbabilityLaw(
        "GAUSSIAN",
        "standard-normal-oracle",
        (ServiceLawComponent("g", 1.0, "GAUSSIAN", 0.0, 1.0),),
    )
    # Published standard-normal integral; tolerance is relative, not a loose absolute epsilon.
    assert isclose(law.threshold_probability(8.0, "GT"), 6.220960574271784e-16, rel_tol=1e-13)
    assert isclose(law.threshold_probability(-8.0, "LT"), 6.220960574271784e-16, rel_tol=1e-13)
    assert law.threshold_probability(1000.0, "GT") == 0.0
    assert law.threshold_probability(-1000.0, "GT") == 1.0
