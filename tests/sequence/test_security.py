"""Static closed stdlib/existing-contract boundary and no executable/provider coupling."""

import ast
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = tuple(sorted((ROOT / "src/afre/sequence").glob("*.py")))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_closed_implementation(path: Path) -> None:
    tree = ast.parse(path.read_text())
    forbidden = {
        "pickle",
        "joblib",
        "socket",
        "urllib",
        "requests",
        "httpx",
        "subprocess",
        "importlib",
        "ame",
        "mce",
        "eie",
        "options_engine",
        "torch",
        "sklearn",
        "tensorflow",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0].lower() for a in node.names} & forbidden
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0].lower() not in forbidden
        elif isinstance(node, ast.Call):
            assert not (
                isinstance(node.func, ast.Name)
                and node.func.id in {"eval", "exec", "compile", "__import__", "open"}
            )
    assert "/Users/" not in path.read_text()


def test_zero_runtime_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["dependencies"] == [] and project["requires-python"] == ">=3.11"
