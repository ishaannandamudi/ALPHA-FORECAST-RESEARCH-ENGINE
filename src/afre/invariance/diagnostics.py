"""Measured parameters of supplied artifacts; no fitting, search, pruning or promotion."""

import json
from math import fsum
from typing import TYPE_CHECKING

from afre.hashing import bytes_digest
from afre.invariance.artifacts import (
    ModelStabilityDiagnostic,
    StabilityParameterRecord,
    StabilityParameterSummary,
)
from afre.invariance.coefficients import parameter_summary, raw_coefficients
from afre.invariance.definitions import EnvironmentSet, StabilityAnalysisSpec
from afre.invariance.schema import ComparabilityStatus
from afre.nonlinear.artifacts import NonlinearModelArtifact
from afre.nonlinear.definitions import NonlinearModelSpec
from afre.orthogonalization.artifacts import ProjectionArtifact
from afre.orthogonalization.definitions import OrthogonalizationSpec
from afre.orthogonalization.evaluation_artifacts import RedundancyEvaluation
from afre.orthogonalization.source_policy import diagnostic_policy_key
from afre.schema import require
from afre.sequence.artifacts import SequenceModelArtifact, SequenceTransformArtifact
from afre.sequence.definitions import SequenceModelSpec
from afre.serialization import canonical_json
from afre.statistical_models.artifacts import FittedModelArtifact, ModelFitInputs
from afre.statistical_models.definitions import BaselineModelSpec
from afre.statistical_models.linear_algebra import finite
from afre.statistical_models.metrics import correlation
from afre.target_engine.definitions import TargetDefinition
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition
from afre.uncertainty.definitions import UncertaintySpec

if TYPE_CHECKING:
    from afre.invariance.repository import InvarianceRepository


def key_for(parts: tuple[object, ...]) -> str:
    return bytes_digest(
        json.dumps(parts, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    )


def record_for(
    repo: "InvarianceRepository",
    env_id: str,
    artifact_id: str,
    target: TargetDefinition,
    raw_scale: bool,
    cutoff_ns: int,
) -> StabilityParameterRecord:
    v = repo.get_any(artifact_id)
    require(
        getattr(v, "available_ns", 0) <= cutoff_ns,
        "parameter artifact unavailable at research cutoff",
    )
    state, reason, values = (
        ComparabilityStatus.COMPARABLE,
        "supplied-frozen-measured-parameters-only",
        {},
    )
    semantics: tuple[object, ...]
    if isinstance(v, FittedModelArtifact):
        s = repo.resolve(BaselineModelSpec, v.spec_id)
        require(s.target == target, "coefficient target/horizon")
        inputs = repo.resolve(ModelFitInputs, v.fit_inputs_id)
        semantics = (
            "linear",
            s.family.value,
            v.feature_ids,
            target.fingerprint,
            v.l1_penalty,
            v.l2_penalty,
            "affine-raw-v1" if raw_scale else inputs.preprocessing_state_ids,
        )
        converted = raw_coefficients(repo, v) if raw_scale else (v.intercept, v.coefficients)
        if converted is None:
            state, reason = (
                ComparabilityStatus.INCOMPARABLE,
                "nonaffine-preprocessing-no-raw-coefficient",
            )
        else:
            intercept, betas = converted
            values = {
                "intercept": intercept,
                **{f"coefficient:{f}": b for f, b in zip(v.feature_ids, betas, strict=True)},
            }
    elif isinstance(v, NonlinearModelArtifact):
        s_n = repo.resolve(NonlinearModelSpec, v.spec_id)
        require(s_n.target == target, "tree/nonlinear target/horizon")
        semantics = (
            "tree" if v.nodes else "nonlinear-readout",
            target.fingerprint,
            v.columns,
            s_n.interaction_set.fingerprint,
            v.transform_ids,
        )
        if v.nodes:
            for node in v.nodes:
                if node.feature_id:
                    name = "split-count:" + node.feature_id
                    values[name] = values.get(name, 0.0) + 1.0
                    assert node.threshold is not None
                    values[f"threshold:{node.feature_id}:{node.node_id}"] = node.threshold
                else:
                    # Signed branch paths are preserved through the immutable tree evidence.
                    path: list[tuple[str, float, str]] = []
                    at = node.node_id
                    while at:
                        parent = next(p for p in v.nodes if p.left == at or p.right == at)
                        assert parent.feature_id is not None and parent.threshold is not None
                        path.append(
                            (
                                parent.feature_id,
                                parent.threshold,
                                "left" if parent.left == at else "right",
                            )
                        )
                        at = parent.node_id
                    path_key = key_for(tuple(reversed(path)))
                    values["path-present:" + path_key] = 1.0
                    values["leaf-support:" + path_key] = float(len(node.sample_ids))
            values["leaf-count"] = float(sum(n.feature_id is None for n in v.nodes))
        elif raw_scale:
            state, reason = (
                ComparabilityStatus.INCOMPARABLE,
                "interaction-basis-raw-underlying-feature-conversion-not-supported",
            )
        else:
            values = {
                "intercept": v.intercept,
                **{
                    f"coefficient:{f}": b
                    for f, b in zip(v.columns, v.coefficients, strict=True)
                },
            }
    elif isinstance(v, SequenceModelArtifact):
        s_q = repo.resolve(SequenceModelSpec, v.spec_id)
        require(s_q.target == target, "sequence target/horizon")
        transform = repo.resolve(SequenceTransformArtifact, v.transform_id)
        semantics = (
            "sequence",
            target.fingerprint,
            v.family.value,
            tuple(f.fingerprint for f in s_q.features),
            s_q.window.fingerprint,
            v.transform_id,
        )
        if raw_scale and any(
            c != 0 or scale != 1
            for c, scale in zip(transform.centers, transform.scales, strict=True)
        ):
            state, reason = (
                ComparabilityStatus.INCOMPARABLE,
                "sequence-center-effect-varies-with-masked-window-weight-no-global-raw-intercept",
            )
        else:
            values = {
                "intercept": v.intercept,
                "fixed-decay-rate-per-second": s_q.decay_rate_per_second,
                "fixed-state-transition": s_q.state_transition,
                "fixed-state-input-gain": s_q.state_input_gain,
                "readout-L1-state-sensitivity": finite(fsum(abs(b) for b in v.coefficients)),
                **{
                    f"readout:{f.fingerprint}": b
                    for f, b in zip(s_q.features, v.coefficients, strict=True)
                },
            }
    elif isinstance(v, ProjectionArtifact):
        s_o = repo.resolve(OrthogonalizationSpec, v.spec_id)
        require(s_o.target == target, "projection target/horizon")
        semantics = (
            "projection",
            target.fingerprint,
            s_o.candidate.fingerprint,
            v.reference_ids,
            s_o.mode.value,
            "affine-raw-v1" if raw_scale else (v.centers, v.scales),
        )
        betas = (
            tuple(finite(b / scale) for b, scale in zip(v.coefficients, v.scales, strict=True))
            if raw_scale
            else v.coefficients
        )
        intercept = (
            finite(v.intercept - fsum(b * c for b, c in zip(betas, v.centers, strict=True)))
            if raw_scale
            else v.intercept
        )
        values = {
            "intercept": intercept,
            "TRAIN-residual-variance": v.train_residual_variance,
            **{f"projection:{f}": b for f, b in zip(v.reference_ids, betas, strict=True)},
        }
    elif isinstance(v, RedundancyEvaluation):
        p = repo.resolve(ProjectionArtifact, v.projection_id)
        s_o = repo.resolve(OrthogonalizationSpec, p.spec_id)
        require(s_o.target == target, "redundancy target/horizon")
        semantics = (
            "redundancy",
            target.fingerprint,
            s_o.candidate.fingerprint,
            p.reference_ids,
            s_o.mode.value,
            v.predictive_pair_id,
        )
        if v.residual_variance_ratio is not None:
            values["residual-variance-ratio"] = v.residual_variance_ratio
        for i, c in enumerate(v.raw_reference_correlations):
            if c.value is not None:
                values["raw-reference-correlation:" + p.reference_ids[i]] = c.value
        for m in v.incremental_metrics:
            if m.value is not None:
                values["incremental:" + m.name.value] = m.value
    else:
        require(
            isinstance(v, ForecastUncertaintyDecomposition),
            "unsupported supplied stability artifact",
        )
        assert isinstance(v, ForecastUncertaintyDecomposition)
        require(
            v.target_id == target.fingerprint and v.horizon_id == target.horizon.fingerprint,
            "uncertainty target/horizon",
        )
        u = repo.resolve(UncertaintySpec, v.spec_id)
        semantics = (
            "uncertainty",
            target.fingerprint,
            tuple(diagnostic_policy_key(repo, u, c) for c in v.components),
            v.closure.value,
        )
        if v.total_variance is not None:
            values["exact-total-predictive-variance"] = v.total_variance
        for component in v.components:
            if component.value is not None:
                values[
                    f"component:{component.component.value}:{component.measure.value}:{component.status.value}"
                ] = component.value
        for k, share in v.shares:
            if share is not None:
                values["exact-component-share:" + k.value] = share
    return StabilityParameterRecord(
        env_id,
        artifact_id,
        str(semantics[0]),
        key_for(semantics),
        tuple(values.items()),
        state,
        reason,
    )


def model_stability_for(
    repo: "InvarianceRepository",
    spec_id: str,
    assignments: tuple[tuple[str, str], ...],
    raw_scale: bool,
    cutoff_ns: int,
    available_ns: int,
) -> ModelStabilityDiagnostic:
    spec = repo.resolve(StabilityAnalysisSpec, spec_id)
    envset = repo.resolve(EnvironmentSet, spec.environment_set_id)
    require(
        2 <= len(assignments) <= repo.invariance_bounds.environments
        and len(set(assignments)) == len(assignments)
        and all(e in {d.fingerprint for d in envset.definitions} for e, _ in assignments)
        and available_ns >= cutoff_ns,
        "bounded supplied declared model assignments",
    )
    records = tuple(
        record_for(repo, e, a, spec.target, raw_scale, cutoff_ns)
        for e, a in sorted(assignments)
    )
    keys = {r.semantic_key for r in records}
    comparable = len(keys) == 1 and all(
        r.status is ComparabilityStatus.COMPARABLE for r in records
    )
    summaries: tuple[StabilityParameterSummary, ...] = ()
    correlations: tuple[tuple[str, str, float | None], ...] = ()
    if comparable:
        unique_records = tuple({r.artifact_id: r for r in records}.values())
        maps = tuple(dict(r.values) for r in unique_records)
        common = set.intersection(*(set(m) for m in maps))
        recurrence = {
            k for m in maps for k in m if k.startswith(("split-count:", "path-present:"))
        }
        names = tuple(sorted(common | recurrence))
        summaries = tuple(
            parameter_summary(n, tuple(m.get(n, 0.0) for m in maps)) for n in names
        )
        coefficients = tuple(
            n for n in names if n.startswith(("coefficient:", "readout:", "projection:"))
        )
        correlations = tuple(
            (
                a.fingerprint,
                b.fingerprint,
                correlation(
                    tuple(dict(a.values)[n] for n in coefficients),
                    tuple(dict(b.values)[n] for n in coefficients),
                ).value,
            )
            for i, a in enumerate(records)
            for b in records[i + 1 :]
        )
    status = (
        ComparabilityStatus.PARTIALLY_COMPARABLE
        if comparable
        else ComparabilityStatus.INCOMPARABLE
    )
    reason = (
        "supplied-fits-descriptive-no-environment-specific-refit-or-causal-proof"
        if comparable
        else "family-feature-preprocessing-policy-or-identifiability-mismatch"
    )
    require(
        sum(len(r.values) for r in records) <= repo.invariance_bounds.shift_cells
        and sum(len(canonical_json(r).encode()) for r in records)
        <= repo.invariance_bounds.serialized_bytes,
        "parameter work/byte bound",
    )
    return ModelStabilityDiagnostic(
        spec_id,
        assignments,
        raw_scale,
        records,
        summaries,
        correlations,
        status,
        reason,
        cutoff_ns,
        available_ns,
    )
