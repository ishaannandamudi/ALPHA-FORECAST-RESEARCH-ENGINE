"""Evidence-specific component methods; unavailable values are never fabricated."""

import math
from typing import TYPE_CHECKING

from afre.event_conditioned.artifacts import EventConditionedForecast
from afre.mixture.artifacts import MixtureDistribution, MixtureForecast
from afre.regime_conditioned.artifacts import RegimeConditionedForecast, RegimeConditionedModel
from afre.schema import require
from afre.statistical_models.linear_algebra import finite, total
from afre.uncertainty.artifacts import (
    ParameterCovariance,
    UncertaintyComponent,
    UncertaintyInterval,
)
from afre.uncertainty.covariance import quadratic_variance
from afre.uncertainty.definitions import UncertaintyRequest, UncertaintySpec
from afre.uncertainty.moments import entropy, mixture_terms, variance, weighted_spread
from afre.uncertainty.parameter import prediction_design
from afre.uncertainty.schema import ClosurePolicy
from afre.uncertainty.schema import IdentifiabilityStatus as Status
from afre.uncertainty.schema import UncertaintyMeasure as Measure
from afre.uncertainty.schema import UncertaintyType as Kind
from afre.uncertainty.sources import ForecastSource, matched_alternatives

if TYPE_CHECKING:
    from afre.uncertainty.repository import UncertaintyRepository


def units(spec: UncertaintySpec, measure: Measure) -> str:
    if measure is Measure.ENTROPY:
        return "nats"
    if measure is Measure.QUALITY_PENALTY:
        return "diagnostic-score"
    squared = measure in (Measure.VARIANCE, Measure.SCORE_VARIANCE)
    return ("target-value-squared:" if squared else "target-value:") + spec.target.fingerprint


def component_for(
    repo: "UncertaintyRepository",
    spec: UncertaintySpec,
    request: UncertaintyRequest,
    source: ForecastSource,
    interval: UncertaintyInterval,
    available_ns: int,
) -> UncertaintyComponent:
    kind, measure = request.component, request.measure
    value: float | None = None
    status, method, reason = (
        Status.UNAVAILABLE,
        "no-evidence-v1",
        "source-does-not-identify-requested-component",
    )
    evidence = [source.artifact.fingerprint]
    samples: tuple[str, ...] = ()
    var = variance(source.law)
    if kind in (Kind.TOTAL_PREDICTIVE, Kind.HORIZON):
        method = (
            "source-predictive-variance-v1"
            if kind is Kind.TOTAL_PREDICTIVE
            else "horizon-specific-predictive-variance-v1"
        )
        if measure in (Measure.VARIANCE, Measure.STANDARD_DEVIATION) and var is not None:
            value = var if measure is Measure.VARIANCE else finite(math.sqrt(var))
            status, reason = Status.IDENTIFIED, "finite-source-law-moment-no-source-attribution"
        elif measure is Measure.INTERVAL_WIDTH and interval.width is not None:
            value, status, method, reason = (
                interval.width,
                Status.IDENTIFIED,
                "source-interval-width-v1",
                interval.semantics,
            )
            evidence.append(interval.fingerprint)
        elif measure not in (
            Measure.VARIANCE,
            Measure.STANDARD_DEVIATION,
            Measure.INTERVAL_WIDTH,
        ):
            status, reason = Status.INCOMPATIBLE, "incompatible-predictive-measure"
    elif kind in (Kind.WITHIN_EXPERT_PREDICTIVE, Kind.EXPERT_DISAGREEMENT):
        if isinstance(source.law, MixtureDistribution) and measure is Measure.VARIANCE:
            _, within, between = mixture_terms(source.law)
            value = within if kind is Kind.WITHIN_EXPERT_PREDICTIVE else between
            method = (
                "finite-mixture-within-v1"
                if kind is Kind.WITHIN_EXPERT_PREDICTIVE
                else "finite-mixture-between-v1"
            )
            status, reason = (
                Status.IDENTIFIED,
                "exact-law-identity-not-automatically-aleatoric-or-epistemic",
            )
            evidence.append(source.law.fingerprint)
        elif isinstance(source.artifact, MixtureForecast) and kind is Kind.EXPERT_DISAGREEMENT:
            contributions = tuple(
                c for c in source.artifact.contributions if c.effective_weight > 0
            )
            weights = tuple(c.effective_weight for c in contributions)
            values = tuple(c.value for c in contributions if c.value is not None)
            if measure is Measure.VARIANCE:
                value = weighted_spread(weights, values)[1]
                method = "weighted-point-expert-spread-proxy-v1"
            elif measure is Measure.DISAGREEMENT:
                value = total(
                    [
                        finite(a * b * abs(x - y))
                        for a, x in zip(weights, values, strict=True)
                        for b, y in zip(weights, values, strict=True)
                    ]
                )
                method = "weighted-pairwise-absolute-disagreement-v1"
            if value is not None:
                status, reason = (
                    Status.PROXY_ONLY,
                    "descriptive-expert-disagreement-not-calibrated-epistemic",
                )
            else:
                status, reason = Status.INCOMPATIBLE, "unsupported-expert-disagreement-measure"
    elif kind in (Kind.PARAMETER, Kind.ALEATORIC):
        method = "explicit-OLS-assumptions-required-v1"
        status, reason = (
            Status.UNIDENTIFIABLE,
            "predictive-variance-alone-does-not-identify-noise-or-parameter-uncertainty",
        )
        if spec.covariance_id is not None:
            estimator = repo.resolve(ParameterCovariance, spec.covariance_id)
            evidence.extend((estimator.fingerprint, estimator.spec_id))
            require(
                estimator.available_ns <= available_ns,
                "uncertainty before covariance availability",
            )
            design = prediction_design(repo, source, estimator)
            samples = estimator.train_sample_ids
            if measure is not Measure.VARIANCE:
                status, reason = Status.INCOMPATIBLE, "OLS-components-support-variance-only"
            elif estimator.status is Status.PARTIALLY_IDENTIFIED:
                assert estimator.residual_variance is not None
                value = (
                    quadratic_variance(design, estimator.covariance)
                    if kind is Kind.PARAMETER
                    else estimator.residual_variance
                )
                status, reason = Status.PARTIALLY_IDENTIFIED, estimator.reason
                method = (
                    "OLS-x-Cov-beta-x-v1"
                    if kind is Kind.PARAMETER
                    else "OLS-SSE-over-n-minus-rank-noise-v1"
                )
            else:
                status, reason = estimator.status, estimator.reason
    elif kind is Kind.MODEL_SPECIFICATION:
        method = "equal-weight-matched-model-spread-proxy-v1"
        alternatives = matched_alternatives(repo, source, spec.alternative_forecast_ids)
        evidence.extend(s.artifact.fingerprint for s in alternatives)
        require(
            all(s.available_ns <= available_ns for s in alternatives),
            "uncertainty before alternative models",
        )
        if measure not in (Measure.VARIANCE, Measure.SCORE_VARIANCE):
            status, reason = Status.INCOMPATIBLE, "model-spread-measure-incompatible"
        elif len(alternatives) < spec.minimum_count:
            status, reason = (
                Status.INSUFFICIENT_DATA,
                "matched-alternative-model-minimum-not-met",
            )
        else:
            value = weighted_spread(
                (1 / len(alternatives),) * len(alternatives),
                tuple(s.prediction for s in alternatives),
                spec.tolerance,
            )[1]
            status, reason = (
                Status.PROXY_ONLY,
                "supplied-alternatives-spread-not-specification-posterior",
            )
    elif kind is Kind.REGIME_AMBIGUITY and isinstance(
        source.artifact, RegimeConditionedForecast
    ):
        membership = source.artifact.membership
        if membership is not None:
            require(
                len(membership.states) <= repo.uncertainty_bounds.experts,
                "regime uncertainty state bound",
            )
            model = repo.resolve(RegimeConditionedModel, source.artifact.model_id)
            evidence.append(model.fingerprint)
            if source.artifact.regime_snapshot_id:
                evidence.append(source.artifact.regime_snapshot_id)
            if measure is Measure.ENTROPY:
                value, status, method = (
                    entropy(membership.weights),
                    Status.IDENTIFIED,
                    "supplied-regime-membership-entropy-v1",
                )
                reason = "discrete-state-entropy-not-return-variance"
            elif measure is Measure.VARIANCE:
                if any(
                    w > 0 and fit.value is None
                    for w, fit in zip(membership.weights, model.state_fits, strict=True)
                ):
                    status, reason = (
                        Status.INSUFFICIENT_DATA,
                        "missing-active-state-conditional-mean",
                    )
                else:
                    value = weighted_spread(
                        membership.weights, tuple(fit.value or 0.0 for fit in model.state_fits)
                    )[1]
                    status, method, reason = (
                        Status.PROXY_ONLY,
                        "supplied-state-mean-spread-v1",
                        "regime-state-ambiguity-not-causal-source-attribution",
                    )
            else:
                status, reason = Status.INCOMPATIBLE, "regime-measure-incompatible"
    elif kind is Kind.EVENT_AMBIGUITY and isinstance(source.artifact, EventConditionedForecast):
        if measure is Measure.DISAGREEMENT:
            value, status, method, reason = (
                abs(source.artifact.shift),
                Status.PROXY_ONLY,
                "conditioned-vs-base-absolute-spread-v1",
                "no-probabilistic-event-hypothesis-model-or-causal-attribution",
            )
        else:
            status, reason = (
                Status.INCOMPATIBLE,
                "event-probabilities-not-supplied-no-invented-variance",
            )
    elif kind is Kind.DATA_QUALITY:
        method = "source-quality-flags-no-numerical-mapping-v1"
        status = (
            Status.UNAVAILABLE if measure is Measure.QUALITY_PENALTY else Status.INCOMPATIBLE
        )
        reason = "quality-states-retained-no-unit-safe-penalty-mapping-implemented"
    elif kind is Kind.RESIDUAL_UNATTRIBUTED:
        status, method, reason = (
            Status.UNIDENTIFIABLE,
            "no-arbitrary-residual-v1",
            "residual-requires-an-explicit-compatible-additive-identity",
        )
    additive = spec.closure is ClosurePolicy.EXACT_ADDITIVE and method in (
        "finite-mixture-within-v1",
        "finite-mixture-between-v1",
    )
    return UncertaintyComponent(
        spec.fingerprint,
        kind,
        measure,
        value,
        units(spec, measure),
        status,
        method,
        reason,
        tuple(evidence),
        samples,
        additive,
        available_ns,
    )
