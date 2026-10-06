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
    assert "**Stop after AFRE-14.**" in master
    assert "**Next scope: AFRE-15 — Forecast Uncertainty Decomposition.**" in readme
    project = tomllib.loads((REPOSITORY / "pyproject.toml").read_text())["project"]
    assert project["version"] == "0.15.0" and project["dependencies"] == []
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
        "mixture-of-experts.md",
        "expert-contracts.md",
        "expert-gating.md",
        "expert-missingness.md",
        "probabilistic-mixtures.md",
        "expert-contributions.md",
        "external-expert-integration.md",
        "mixture-benchmark.md",
        "regime-conditioned-forecasting.md",
        "regime-snapshots.md",
        "hard-soft-regimes.md",
        "regime-transitions.md",
        "regime-conditioned-calibration.md",
        "regime-drift.md",
        "external-regime-integration.md",
        "regime-conditioned-benchmark.md",
        "event-conditioned-forecasting.md",
        "event-time-semantics.md",
        "event-windows.md",
        "event-surprise-materiality-novelty.md",
        "event-overlap.md",
        "event-conditioned-evaluation.md",
        "event-reaction-signals.md",
        "event-conditioned-benchmark.md",
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
        "research-datasets.md",
        "leakage-safe-splitting.md",
        "purged-walk-forward.md",
        "embargo-semantics.md",
        "fold-local-preprocessing.md",
        "dataset-contamination-audits.md",
        "statistical-baselines.md",
        "model-fit-semantics.md",
        "linear-models.md",
        "regularization-semantics.md",
        "point-forecast-evaluation.md",
        "model-reproducibility.md",
        "probabilistic-forecasting.md",
        "forecast-distributions.md",
        "quantile-forecasts.md",
        "threshold-probabilities.md",
        "proper-scoring-rules.md",
        "probabilistic-evaluation.md",
        "forecast-calibration.md",
        "probability-calibration.md",
        "quantile-calibration.md",
        "conformal-calibration.md",
        "calibration-partitions.md",
        "calibration-drift.md",
        "multi-horizon-forecasting.md",
        "horizon-sets.md",
        "cross-horizon-dependence.md",
        "multi-horizon-consistency.md",
        "multi-horizon-evaluation.md",
        "horizon-specific-calibration.md",
        "cross-sectional-ranking.md",
        "cross-sectional-normalization.md",
        "information-coefficient.md",
        "group-neutral-ranking.md",
        "rank-stability.md",
        "external-signal-integration.md",
        "point-in-time-universe.md",
        "cross-sectional-benchmark.md",
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
    dataset_report = (REPOSITORY / "docs/AFRE_4_COMPLETION_REPORT.md").read_text()
    for label in labels:
        assert re.search(rf"^\| {label} \|", dataset_report, re.MULTILINE), (
            f"missing dataset report item {label}"
        )
    model_report = (REPOSITORY / "docs/AFRE_5_COMPLETION_REPORT.md").read_text()
    model_labels = (*labels, "AT", "AU", "AV")
    assert re.findall(r"^\| ([A-Z]{1,2}) \|", model_report, re.MULTILINE) == list(
        model_labels
    ), "model report must have exactly the 48 A–AV items in order"
    probability_report = (REPOSITORY / "docs/AFRE_6_COMPLETION_REPORT.md").read_text()
    assert re.findall(r"^\| ([A-Z]{1,2}) \|", probability_report, re.MULTILINE) == list(
        (*labels, "AT", "AU")
    ), "probabilistic report must have exactly the 47 A–AU items in order"
    calibration_report = (REPOSITORY / "docs/AFRE_7_COMPLETION_REPORT.md").read_text()
    assert re.findall(r"^\| ([A-Z]{1,2}) \|", calibration_report, re.MULTILINE) == list(
        (*labels, "AT", "AU", "AV", "AW")
    ), "calibration report must have exactly the 49 A–AW items in order"
    multihorizon_report = (REPOSITORY / "docs/AFRE_8_COMPLETION_REPORT.md").read_text()
    assert re.findall(r"^\| ([A-Z]{1,2}) \|", multihorizon_report, re.MULTILINE) == list(
        (*labels, "AT", "AU", "AV", "AW")
    ), "multi-horizon report must have exactly the 49 A–AW items in order"
    cross_section_report = (REPOSITORY / "docs/AFRE_9_COMPLETION_REPORT.md").read_text()
    cross_section_labels = (
        *tuple(chr(index) for index in range(ord("A"), ord("Z") + 1)),
        *tuple("A" + chr(index) for index in range(ord("A"), ord("Z") + 1)),
        *tuple("B" + chr(index) for index in range(ord("A"), ord("E") + 1)),
    )
    assert re.findall(r"^\| ([A-Z]{1,2}) \|", cross_section_report, re.MULTILINE) == list(
        cross_section_labels
    ), "cross-sectional report must have exactly the 57 A–BE items in order"
    event_report = (REPOSITORY / "docs/AFRE_10_COMPLETION_REPORT.md").read_text()
    event_labels = (*cross_section_labels[:52], "BA", "BB", "BC")
    assert re.findall(r"^\| ([A-Z]{1,2}) \|", event_report, re.MULTILINE) == list(event_labels)
    assert (REPOSITORY / "docs/event-conditioned-profile.json").is_file()
    regime_report = (REPOSITORY / "docs/AFRE_11_COMPLETION_REPORT.md").read_text()
    regime_labels = (
        *cross_section_labels[:52],
        *("B" + chr(index) for index in range(ord("A"), ord("K") + 1)),
    )
    assert re.findall(r"^\| ([A-Z]{1,2}) \|", regime_report, re.MULTILINE) == list(
        regime_labels
    )
    assert (REPOSITORY / "docs/regime-conditioned-profile.json").is_file()
    mixture_report = (REPOSITORY / "docs/AFRE_12_COMPLETION_REPORT.md").read_text()
    mixture_labels = (
        *cross_section_labels[:52],
        *("B" + chr(index) for index in range(ord("A"), ord("O") + 1)),
    )
    assert re.findall(r"^\| ([A-Z]{1,2}) \|", mixture_report, re.MULTILINE) == list(
        mixture_labels
    )
    nonlinear_report = (REPOSITORY / "docs/AFRE_13_COMPLETION_REPORT.md").read_text()
    nonlinear_labels = (
        *cross_section_labels[:52],
        *("B" + chr(i) for i in range(ord("A"), ord("I") + 1)),
    )
    assert re.findall(r"^\| ([A-Z]{1,2}) \|", nonlinear_report, re.MULTILINE) == list(
        nonlinear_labels
    )
    for name in (
        "nonlinear-feature-interactions.md",
        "interaction-definitions.md",
        "nonlinear-transforms.md",
        "shallow-tree-models.md",
        "interaction-stability.md",
        "cross-domain-interactions.md",
        "nonlinear-evaluation.md",
        "nonlinear-benchmark.md",
        "nonlinear-profile.json",
    ):
        assert (REPOSITORY / "docs" / name).is_file()
    sequence_report = (REPOSITORY / "docs/AFRE_14_COMPLETION_REPORT.md").read_text()
    sequence_labels = (
        *cross_section_labels[:52],
        *("B" + chr(i) for i in range(ord("A"), ord("T") + 1)),
    )
    assert re.findall(r"^\| ([A-Z]{1,2}) \|", sequence_report, re.MULTILINE) == list(
        sequence_labels
    )
    for name in (
        "temporal-sequence-models.md",
        "sequence-windows.md",
        "sequence-masking.md",
        "sequence-time-encoding.md",
        "causal-sequence-training.md",
        "sequence-model-families.md",
        "external-sequence-integration.md",
        "sequence-evaluation.md",
        "sequence-benchmark.md",
        "sequence-profile.json",
    ):
        assert (REPOSITORY / "docs" / name).is_file()
    assert (REPOSITORY / "docs/mixture-profile.json").is_file()
    assert (REPOSITORY / "docs/cross-sectional-profile.json").is_file()
    for text in (master, readme):
        assert (
            "AFRE-6 evaluates calibration diagnostics but does NOT fit "
            "calibration transformations." in text
        )
        assert not re.search(r"AFRE-6 (?:is deferred|work is implemented)", text)
    from afre.version import (
        CALIBRATION_SCHEMA_VERSION,
        CROSS_SECTIONAL_SCHEMA_VERSION,
        DATASET_SCHEMA_VERSION,
        ENGINE_VERSION,
        EVENT_CONDITIONED_SCHEMA_VERSION,
        FEATURE_STORE_SCHEMA_VERSION,
        FOUNDATION_SCHEMA_VERSION,
        MIXTURE_SCHEMA_VERSION,
        MODEL_SCHEMA_VERSION,
        MULTIHORIZON_SCHEMA_VERSION,
        NONLINEAR_SCHEMA_VERSION,
        PROBABILISTIC_SCHEMA_VERSION,
        REGIME_CONDITIONED_SCHEMA_VERSION,
        SEQUENCE_SCHEMA_VERSION,
        STORE_SCHEMA_VERSION,
        STORE_USER_VERSION,
        TARGET_SCHEMA_VERSION,
        UNIVERSE_SCHEMA_VERSION,
    )

    assert ENGINE_VERSION == "0.15.0"
    assert (
        NONLINEAR_SCHEMA_VERSION
        == FOUNDATION_SCHEMA_VERSION
        == FEATURE_STORE_SCHEMA_VERSION
        == TARGET_SCHEMA_VERSION
        == UNIVERSE_SCHEMA_VERSION
        == DATASET_SCHEMA_VERSION
        == MODEL_SCHEMA_VERSION
        == PROBABILISTIC_SCHEMA_VERSION
        == CALIBRATION_SCHEMA_VERSION
        == MULTIHORIZON_SCHEMA_VERSION
        == CROSS_SECTIONAL_SCHEMA_VERSION
        == EVENT_CONDITIONED_SCHEMA_VERSION
        == MIXTURE_SCHEMA_VERSION
        == REGIME_CONDITIONED_SCHEMA_VERSION
        == "1.0"
    )
    assert STORE_SCHEMA_VERSION == "1.14" and STORE_USER_VERSION == 15
    assert SEQUENCE_SCHEMA_VERSION == "1.0"
    print(
        f"PASS: {len(documents)} documents; exact 26-phase roadmap; "
        "versions, links, historical reports and current 72-item A–BT scope"
    )


if __name__ == "__main__":
    main()
