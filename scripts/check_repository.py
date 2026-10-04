"""Offline secret, unfinished-work, whitespace and security-boundary checks."""

import ast
import re
import subprocess
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = (
    re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
    re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api_key|password|secret_token)\s*[:=]\s*[\"\'][^\"\']{8,}[\"\']"),
)
UNFINISHED = re.compile(r"(?im)^\s*(?:#|//|<!--)?\s*(?:TO" + r"DO|FIX" + r"ME)\b")


def main() -> None:
    listing = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=REPOSITORY,
        capture_output=True,
        check=True,
    )
    paths = sorted(set(listing.stdout.decode().split("\0")) - {""})
    failures: list[str] = []
    package = REPOSITORY / "src" / "afre"
    for name in paths:
        path = REPOSITORY / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            failures.append(f"{name}: possible secret")
        if UNFINISHED.search(text):
            failures.append(f"{name}: unfinished-work marker")
        if any(line.rstrip() != line for line in text.splitlines()):
            failures.append(f"{name}: trailing whitespace")
        if text and not text.endswith("\n"):
            failures.append(f"{name}: missing final newline")
        if path.parent == package and path.suffix == ".py":
            for node in ast.walk(ast.parse(text)):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in ("eval", "exec", "__import__")
                ):
                    failures.append(f"{name}: executable data boundary")
    whitespace = subprocess.run(
        ["git", "diff", "--check"], cwd=REPOSITORY, capture_output=True, text=True, check=False
    )
    if whitespace.returncode:
        failures.append(whitespace.stdout + whitespace.stderr)
    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"PASS: {len(paths)} deliverables checked for secrets, unfinished work and whitespace"
    )


if __name__ == "__main__":
    main()
