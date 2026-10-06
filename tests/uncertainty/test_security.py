"""Closed structured data, stdlib runtime and external-engine/network exclusion."""

import ast
import tomllib
from pathlib import Path

import pytest

from afre.schema import ContractError
from afre.serialization import deserialize


def test_no_executable_or_network_surfaces() -> None:
    root = Path(__file__).resolve().parents[2]
    forbidden = {"eval", "exec", "__import__", "compile"}
    excluded = {
        "pickle",
        "joblib",
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "importlib",
        "os",
        "numpy",
        "scipy",
        "torch",
        "ame",
        "mce",
        "eie",
    }
    for path in (root / "src/afre/uncertainty").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden
            if isinstance(node, ast.Import):
                assert not any(n.name.split(".")[0] in excluded for n in node.names)
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in excluded
    assert tomllib.loads((root / "pyproject.toml").read_text())["project"]["dependencies"] == []


@pytest.mark.parametrize(
    "payload",
    [
        '{"type":"ExecutableUncertainty","code":"bad"}',
        '{"$type":"UncertaintySpec","$schema":"99.0"}',
        '__import__("os")',
    ],
)
def test_unknown_executable_payload(payload: str) -> None:
    with pytest.raises((ContractError, ValueError, TypeError)):
        deserialize(payload)
