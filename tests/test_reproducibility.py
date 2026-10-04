import ast
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from examples.foundation_demo import Demo, main


@pytest.mark.parametrize("seed", ["0", "1", "42", "random"])
def test_hash_seed_subprocess(demo: Demo, seed: str) -> None:
    script = """
import socket

def denied(*args, **kwargs):
    raise AssertionError('network forbidden in child process')

socket.socket = denied
socket.getaddrinfo = denied
from examples.foundation_demo import build_demo
print(build_demo().experiment.fingerprint)
"""
    environment = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH="src:.")
    process = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    assert process.stdout.strip() == demo.experiment.fingerprint


def test_example(capsys: pytest.CaptureFixture[str]) -> None:
    main()
    output = capsys.readouterr().out
    assert "Future feature rejected" in output
    assert "fingerprints unchanged" in output


def test_sockets_and_dns_blocked() -> None:
    with pytest.raises(AssertionError, match="network"):
        socket.socket()
    with pytest.raises(AssertionError, match="network"):
        socket.getaddrinfo("example.com", 443)


def test_package_security_boundary() -> None:
    prohibited_imports = {"pickle", "subprocess", "socket", "urllib", "requests", "importlib"}
    prohibited_calls = {"eval", "exec", "__import__"}
    package = Path(__file__).resolve().parents[1] / "src" / "afre"
    for source in package.glob("*.py"):
        tree = ast.parse(source.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(
                    item.name.split(".")[0] not in prohibited_imports for item in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in prohibited_imports
                assert "event_intelligence_engine" not in (node.module or "")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in prohibited_calls
