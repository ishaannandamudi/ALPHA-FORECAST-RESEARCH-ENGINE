"""Offline check of frozen roadmap, versions, AFRE-1 scope and local doc links."""

import re
import tomllib
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
PHASES = (
    "Foundation, Contracts & Temporal Semantics",
    "Point-in-Time Feature Store",
    "Forecast Targets & Label Construction",
    "Point-in-Time Universe & Security Eligibility",
    "Dataset Builder & Leakage-Safe Splitting",
    "Statistical Baseline Models",
    "Probabilistic Forecasting",
    "Forecast Calibration",
    "Multi-Horizon Forecast Architecture",
    "Cross-Sectional Alpha & Ranking",
    "Event-Conditioned Forecasting",
    "Regime-Conditioned Models",
    "Mixture of Experts",
    "Nonlinear Feature Interactions",
    "Temporal / Sequence Models",
    "Forecast Uncertainty Decomposition",
    "Signal Orthogonalization & Redundancy Analysis",
    "Invariance & Stability Research",
    "Transaction-Cost-Aware Research Evaluation",
    "Multiple Testing & Research Overfitting Controls",
    "Hyperparameter & Model Selection Framework",
    "Ensemble & Signal Fusion",
    "Drift, Decay & Model Health",
    "Champion/Challenger & Shadow Evaluation",
    "Forecast Snapshot, Registry & Service",
    "Final Integration, Hardening & Research Audit",
)


def main() -> None:
    master = (REPOSITORY / "docs/AFRE_MASTER_SPEC.md").read_text()
    rows = re.findall(r"^\| AFRE-(\d+) \| ([^|]+) \|", master, re.MULTILINE)
    assert [(index, name.strip()) for index, name in rows] == [
        (str(index), name) for index, name in enumerate(PHASES)
    ]
    readme = (REPOSITORY / "README.md").read_text()
    for text in (master, readme):
        assert "26 distinct phases, AFRE-0 through AFRE-25" in text
        assert "Forecast Targets & Label Construction" in text
    assert "**Stop after AFRE-1.**" in master
    assert "**Next scope: AFRE-2" in readme
    project = tomllib.loads((REPOSITORY / "pyproject.toml").read_text())["project"]
    assert project["version"] == "0.2.0" and project["dependencies"] == []
    documents = (REPOSITORY / "README.md", *sorted((REPOSITORY / "docs").glob("*.md")))
    for document in documents:
        text = document.read_text()
        assert not re.search(r"\b21[ -]phases?\b|AFRE-0 through AFRE-20", text)
        for link in re.findall(r"\]\(([^)]+)\)", text):
            if "://" in link or link.startswith("#"):
                continue
            target = link.split("#", 1)[0]
            assert (document.parent / target).exists(), f"{document.name}: broken {link}"
    for name in (
        "point-in-time-feature-store.md",
        "feature-vintages.md",
        "feature-computation-dag.md",
        "point-in-time-joins.md",
        "feature-normalization.md",
    ):
        assert (REPOSITORY / "docs" / name).is_file()
    report = (REPOSITORY / "docs/AFRE_1_COMPLETION_REPORT.md").read_text()
    labels = (
        *tuple(chr(index) for index in range(ord("A"), ord("Z") + 1)),
        *tuple("A" + chr(index) for index in range(ord("A"), ord("S") + 1)),
    )
    for label in labels:
        assert re.search(rf"^\| {label} \|", report, re.MULTILINE), (
            f"missing report item {label}"
        )
    print(
        f"PASS: {len(documents)} documents; exact 26-phase roadmap; "
        "versions, links and A–AS scope"
    )


if __name__ == "__main__":
    main()
