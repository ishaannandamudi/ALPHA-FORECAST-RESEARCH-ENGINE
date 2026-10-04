"""Offline check of frozen roadmap, versions, completed scopes and local doc links."""

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
    assert "**Stop after AFRE-3.**" in master
    assert "**Next scope: AFRE-4 — Dataset Builder & Leakage-Safe Splitting.**" in readme
    project = tomllib.loads((REPOSITORY / "pyproject.toml").read_text())["project"]
    assert project["version"] == "0.4.0" and project["dependencies"] == []
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
        "forecast-targets.md",
        "target-window-semantics.md",
        "target-availability.md",
        "target-corporate-actions.md",
        "target-lineage.md",
        "security-master.md",
        "security-identity.md",
        "point-in-time-universes.md",
        "universe-membership-vintages.md",
        "security-eligibility.md",
        "survivorship-bias-controls.md",
        "universe-benchmark.md",
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
    target_report = (REPOSITORY / "docs/AFRE_2_COMPLETION_REPORT.md").read_text()
    for label in labels[:43]:
        assert re.search(rf"^\| {label} \|", target_report, re.MULTILINE), (
            f"missing target report item {label}"
        )
    universe_report = (REPOSITORY / "docs/AFRE_3_COMPLETION_REPORT.md").read_text()
    for label in (*labels, "AT"):
        assert re.search(rf"^\| {label} \|", universe_report, re.MULTILINE), (
            f"missing universe report item {label}"
        )
    from afre.version import (
        ENGINE_VERSION,
        FEATURE_STORE_SCHEMA_VERSION,
        FOUNDATION_SCHEMA_VERSION,
        STORE_SCHEMA_VERSION,
        STORE_USER_VERSION,
        TARGET_SCHEMA_VERSION,
        UNIVERSE_SCHEMA_VERSION,
    )

    assert ENGINE_VERSION == "0.4.0"
    assert (
        FOUNDATION_SCHEMA_VERSION
        == FEATURE_STORE_SCHEMA_VERSION
        == TARGET_SCHEMA_VERSION
        == UNIVERSE_SCHEMA_VERSION
        == "1.0"
    )
    assert STORE_SCHEMA_VERSION == "1.3" and STORE_USER_VERSION == 4
    print(
        f"PASS: {len(documents)} documents; exact 26-phase roadmap; "
        "versions, links, historical reports and current A–AT scope"
    )


if __name__ == "__main__":
    main()
