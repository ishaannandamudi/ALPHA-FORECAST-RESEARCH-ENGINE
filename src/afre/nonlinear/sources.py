"""Exact causal scalar projections of unchanged neutral feature/event/regime/expert data."""

from typing import TYPE_CHECKING

from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.schema import SignalQuality
from afre.event_conditioned.events import EventReference, EventSurprise
from afre.feature_store.models import AvailabilityEvidence, FeatureVintage
from afre.features import DataQuality, MissingState
from afre.forecast import ForecastOrigin
from afre.mixture.artifacts import MixtureForecast
from afre.mixture.experts import ExpertForecastBinding, ExpertReference, ExternalExpertForecast
from afre.mixture.schema import ExpertQuality
from afre.nonlinear.artifacts import NonlinearInput, ScalarInput
from afre.nonlinear.definitions import NonlinearModelSpec, ScalarFeatureDefinition
from afre.nonlinear.schema import ScalarSourceKind
from afre.regime_conditioned.regimes import RegimeSnapshot
from afre.regime_conditioned.schema import RegimeQuality, RegimeStateSemantics
from afre.research_datasets.samples import ResearchSample
from afre.research_datasets.schema import Partition
from afre.schema import require
from afre.statistical_models.linear_algebra import finite

if TYPE_CHECKING:
    from afre.nonlinear.repository import NonlinearRepository


def delivery(clocks: AvailabilityEvidence, approved: tuple[str, ...]) -> None:
    proof = clocks.historical_delivery
    require(
        proof is None or proof.attestor in approved, "unapproved nonlinear historical delivery"
    )


def scalar_for(
    repo: "NonlinearRepository",
    source_id: str,
    origin: ForecastOrigin,
    selector: str = "value",
    approved: tuple[str, ...] = (),
) -> ScalarInput:
    source = repo.get_any(source_id)
    value: object
    key: tuple[str, ...]
    if isinstance(source, FeatureVintage):
        delivery(source.clocks, approved)
        require(
            selector == "value"
            and source.entity == origin.instrument
            and source.effective_ns <= origin.timestamp_ns
            and (source.valid_until_ns is None or origin.timestamp_ns < source.valid_until_ns),
            "scalar feature security/effective interval",
        )
        kind = ScalarSourceKind.FEATURE
        key = (source.feature.fingerprint, source.feature.definition.fingerprint)
        unit = source.feature.definition.unit
        value = (
            source.value
            if source.state is MissingState.PRESENT and source.quality is DataQuality.VERIFIED
            else None
        )
        require(value is None or type(value) in (int, float), "numeric scalar feature")
        available = source.clocks.final_available_ns
    elif isinstance(source, ExternalSignal):
        delivery(source.clocks, approved)
        require(
            selector == "value"
            and source.security.instrument == origin.instrument
            and source.as_of_ns <= origin.timestamp_ns,
            "external scalar security/asof",
        )
        kind = ScalarSourceKind.EXTERNAL_SIGNAL
        key = (
            source.provider_name,
            source.provider_version,
            source.provider_schema,
            source.signal_name,
            source.signal_version,
            source.signal_semantics,
        )
        unit = source.unit
        value = source.value if source.quality is SignalQuality.VALID else None
        available = source.clocks.final_available_ns
    elif isinstance(source, EventReference):
        delivery(source.clocks, approved)
        require(
            source.subject.security is not None
            and source.subject.security.instrument == origin.instrument,
            "event scalar requires exact security scope",
        )
        require(selector in ("surprise", "materiality", "novelty"), "event scalar selector")
        attr = getattr(source, selector)
        require(attr is not None, "event attribute absent")
        kind = ScalarSourceKind.EVENT_ATTRIBUTE
        key = (
            source.provider,
            source.provider_version,
            source.event_schema,
            *attr.semantic_key,
        )
        if isinstance(attr, EventSurprise):
            delivery(attr.actual.clocks, approved)
            delivery(attr.expected.clocks, approved)
            available = max(source.clocks.final_available_ns, attr.available_ns)
            unit = "1"
        else:
            delivery(attr.clocks, approved)
            available = max(source.clocks.final_available_ns, attr.clocks.final_available_ns)
            unit = attr.unit
        value = attr.value if source.quality is SignalQuality.VALID else None
    elif isinstance(source, RegimeSnapshot):
        delivery(source.clocks, approved)
        require(
            source.subject.entity == origin.instrument
            and source.subject.security is not None
            and source.as_of_ns <= origin.timestamp_ns
            and source.semantics is RegimeStateSemantics.FILTERED,
            "causal security regime scalar",
        )
        weights = dict(zip(source.membership.states, source.membership.weights, strict=True))
        require(selector in weights, "exact regime state selector")
        kind = ScalarSourceKind.REGIME_PROBABILITY
        key = (source.taxonomy.fingerprint, selector)
        unit = "1"
        value = weights[selector] if source.quality is RegimeQuality.VALID else None
        available = source.clocks.final_available_ns
    elif isinstance(source, ExpertForecastBinding):
        require(
            selector == "value" and source.origin == origin, "expert scalar exact full origin"
        )
        repo._validate_links(source)
        expert = repo.resolve(ExpertReference, source.expert_id)
        external = repo.get_any(source.forecast_id)
        if isinstance(external, ExternalExpertForecast):
            delivery(external.clocks, approved)
        kind = ScalarSourceKind.EXPERT_POINT
        key = (expert.fingerprint, source.target_definition_id)
        unit = "exact-target-unit:" + source.target_definition_id
        value = source.point if source.quality is ExpertQuality.VALID else None
        available = source.available_ns
    else:
        require(isinstance(source, MixtureForecast), "unsupported nonlinear scalar source")
        assert isinstance(source, MixtureForecast)
        require(selector == "value" and source.origin == origin, "mixture scalar exact origin")
        kind = ScalarSourceKind.MIXTURE_POINT
        key = (
            source.request.expert_set_id,
            source.request.gate_id,
            source.target_definition_id,
        )
        unit = "exact-target-unit:" + source.target_definition_id
        value = source.value
        available = source.available_ns
    require(value is None or type(value) in (int, float), "numeric scalar source")
    assert value is None or isinstance(value, (int, float))
    definition = ScalarFeatureDefinition(kind, key, selector, unit)
    return ScalarInput(
        definition,
        source_id,
        origin,
        finite(float(value)) if value is not None else None,
        available,
        approved,
    )


def input_for(
    repo: "NonlinearRepository", sample_id: str, scalar_ids: tuple[str, ...]
) -> NonlinearInput:
    sample = repo.resolve(ResearchSample, sample_id)
    require(
        sample.origin is not None and not sample.dropped, "nonlinear admitted sample origin"
    )
    assert sample.origin is not None
    require(
        0 < len(scalar_ids) <= repo.nonlinear_bounds.features, "nonlinear input feature bound"
    )
    return NonlinearInput(
        sample_id, sample.origin, tuple(repo.resolve(ScalarInput, i) for i in scalar_ids)
    )


def validate_input(
    repo: "NonlinearRepository", value: NonlinearInput, spec: NonlinearModelSpec | None = None
) -> Partition | None:
    sample = repo.resolve(ResearchSample, value.sample_id)
    require(
        not sample.dropped and sample.origin == value.origin,
        "input admitted exact sample origin",
    )
    if spec:
        require(
            sample.target_definition_id == spec.target.fingerprint
            and tuple(s.definition for s in value.scalars) == spec.features,
            "exact nonlinear feature/target set",
        )
    for scalar in value.scalars:
        approved = scalar.approved_attestors
        require(
            spec is None or set(approved) <= set(spec.approved_delivery_attestors),
            "scalar attestors not approved by model",
        )
        require(
            scalar
            == scalar_for(
                repo, scalar.source_id, value.origin, scalar.definition.selector, approved
            ),
            "nonlinear exact scalar evidence",
        )
        if scalar.definition.kind is ScalarSourceKind.FEATURE:
            require(
                scalar.source_id in sample.feature_vintage_ids,
                "ordinary scalar must pin AFRE-4 selected vintage",
            )
        if (
            scalar.definition.kind
            in (ScalarSourceKind.EXPERT_POINT, ScalarSourceKind.MIXTURE_POINT)
            and spec
        ):
            require(
                scalar.definition.source_key[-1] == spec.target.fingerprint,
                "expert scalar target/horizon",
            )
    if spec is None:
        return None
    matches = tuple(
        m for m in repo.fold_memberships(spec.fold_id) if m.sample_id == sample.fingerprint
    )
    require(len(matches) == 1, "input exact fold membership")
    return matches[0].partition
