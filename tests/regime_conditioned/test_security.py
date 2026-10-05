"""The new runtime boundary stays data-only, provider-neutral and dependency-free."""

import ast
from pathlib import Path


def test_no_upstream_runtime_coupling() -> None:
    folder = Path(__file__).resolve().parents[2] / "src/afre/regime_conditioned"
    for path in folder.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                names = []
            assert not any(
                name.lower().split(".")[0]
                in {
                    "mce",
                    "ame",
                    "hmm",
                    "hmmlearn",
                    "pickle",
                    "joblib",
                    "subprocess",
                    "requests",
                    "httpx",
                    "socket",
                    "importlib",
                }
                for name in names
            )
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in {"eval", "exec", "compile", "__import__"}
        assert "../" not in path.read_text()
