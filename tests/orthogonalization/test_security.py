"""Closed structured serialization, no provider execution, imports, network or dependencies."""

import ast
import tomllib
from pathlib import Path

import pytest

from afre.schema import ContractError
from afre.serialization import deserialize


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        "[]",
        "null",
        '{"artifact":{"$type":"UnknownExecutable","fields":{}},"schema_version":"1.0"}',
    ],
)
def test_closed_payload(payload: str) -> None:
    with pytest.raises((ContractError, ValueError)):
        deserialize(payload)


def test_zero_runtime_dependencies_and_external_boundaries() -> None:
    root = Path(__file__).resolve().parents[2]
    assert tomllib.loads((root / "pyproject.toml").read_text())["project"]["dependencies"] == []
    forbidden = {
        "numpy",
        "sklearn",
        "pickle",
        "joblib",
        "subprocess",
        "socket",
        "requests",
        "urllib",
        "ame",
        "mce",
        "eie",
        "options_engine",
    }
    for path in (root / "src/afre/orthogonalization").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] not in forbidden for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in ("eval", "exec", "__import__")
