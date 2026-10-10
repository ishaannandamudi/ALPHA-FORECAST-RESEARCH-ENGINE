"""Explicit affine readouts, tree structure and original fusion weight diagnostics."""

from typing import TYPE_CHECKING

from afre.fusion.artifacts import FusionArtifact
from afre.fusion.contributions import weight_diagnostics
from afre.invariance.coefficients import raw_coefficients
from afre.nonlinear.artifacts import NonlinearModelArtifact
from afre.orthogonalization.artifacts import ProjectionArtifact
from afre.schema import Artifact
from afre.sequence.artifacts import SequenceModelArtifact
from afre.sequence.definitions import SequenceModelSpec
from afre.sequence.schema import SequencePreprocessing
from afre.statistical_models.artifacts import FittedModelArtifact

if TYPE_CHECKING:
    from afre.health.repository import HealthRepository


def parameter_values(
    repo: "HealthRepository", raw: Artifact
) -> tuple[tuple[str, float | None], ...]:
    if isinstance(raw, FittedModelArtifact):
        result = raw_coefficients(repo, raw)
        if result is None:
            return (("incomparable_parameters", None),)
        intercept, coefficients = result
        return (
            ("intercept", intercept),
            *(
                ("parameter:" + k, v)
                for k, v in zip(raw.feature_ids, coefficients, strict=True)
            ),
        )
    if isinstance(raw, FusionArtifact):
        dominance, effective, entropy = weight_diagnostics(raw.weights)
        scales = raw.scales or tuple(1.0 for _ in raw.weights)
        centers = raw.centers or tuple(0.0 for _ in raw.weights)
        coefficients = tuple(w / s for (_, w), s in zip(raw.weights, scales, strict=True))
        intercept = raw.intercept - sum(
            c * m for c, m in zip(coefficients, centers, strict=True)
        )
        return (
            ("intercept", intercept),
            ("dominance", dominance),
            ("effective_count", effective),
            ("entropy", entropy),
            *(("weight:" + k, w) for k, w in raw.weights),
            *(
                ("parameter:" + k, c)
                for (k, _), c in zip(raw.weights, coefficients, strict=True)
            ),
        )
    if isinstance(raw, NonlinearModelArtifact):
        if raw.nodes:
            values: list[tuple[str, float | None]] = []
            counts: dict[str, int] = {}
            for node in raw.nodes:
                if node.feature_id is not None:
                    counts[node.feature_id] = counts.get(node.feature_id, 0) + 1
                    values.append(
                        (
                            "threshold:" + str(node.node_id) + ":" + node.feature_id,
                            node.threshold,
                        )
                    )
                else:
                    values.append(
                        ("leaf_support:" + str(node.node_id), float(len(node.sample_ids)))
                    )
            nodes = {node.node_id: node for node in raw.nodes}

            def paths(identity: int, prefix: str) -> None:
                node = nodes[identity]
                if node.feature_id is None:
                    values.append(("path:" + prefix + "/leaf", 1.0))
                else:
                    assert node.left is not None and node.right is not None
                    paths(node.left, prefix + "/" + node.feature_id + ":L")
                    paths(node.right, prefix + "/" + node.feature_id + ":R")

            paths(min(nodes), "root")
            return tuple(values) + tuple(("split:" + k, float(v)) for k, v in counts.items())
        coefficients = tuple(b / s for b, s in zip(raw.coefficients, raw.scales, strict=True))
        intercept = raw.intercept - sum(
            c * m for c, m in zip(coefficients, raw.centers, strict=True)
        )
        return (
            ("intercept", intercept),
            *(("parameter:" + k, c) for k, c in zip(raw.columns, coefficients, strict=True)),
        )
    if isinstance(raw, SequenceModelArtifact):
        spec = repo.resolve(SequenceModelSpec, raw.spec_id)
        if spec.preprocessing is not SequencePreprocessing.NONE:
            return (
                ("incomparable_parameters", None),
                ("sequence_decay", spec.decay_rate_per_second),
            )
        return (
            ("intercept", raw.intercept),
            ("sequence_decay", spec.decay_rate_per_second),
            *(
                ("parameter:" + f.fingerprint, c)
                for f, c in zip(spec.features, raw.coefficients, strict=True)
            ),
        )
    if isinstance(raw, ProjectionArtifact):
        if any(c != 0 for c in raw.centers) or any(s != 1 for s in raw.scales):
            return (("incomparable_parameters", None),)
        return (
            ("intercept", raw.intercept),
            *(
                ("parameter:" + k, c)
                for k, c in zip(raw.reference_ids, raw.coefficients, strict=True)
            ),
        )
    return (("unsupported_parameters", None),)
