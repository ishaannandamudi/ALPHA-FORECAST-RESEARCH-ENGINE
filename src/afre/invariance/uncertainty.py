"""Existing AFRE-15 identifiability is retained; only exact additive terms have shares."""

from typing import TYPE_CHECKING

from afre.invariance.definitions import StabilityAnalysisSpec
from afre.invariance.schema import StabilityMetricName
from afre.orthogonalization.source_policy import diagnostic_policy_key
from afre.schema import require
from afre.uncertainty.artifacts import ForecastUncertaintyDecomposition
from afre.uncertainty.definitions import UncertaintySpec
from afre.uncertainty.schema import UncertaintyMeasure, UncertaintyType
from afre.uncertainty.sources import ForecastSource

if TYPE_CHECKING:
    from afre.invariance.repository import InvarianceRepository


def uncertainty_score(
    repo: "InvarianceRepository",
    spec: StabilityAnalysisSpec,
    sources: tuple[ForecastSource, ...],
    name: StabilityMetricName,
) -> tuple[tuple[float, ...] | None, str]:
    decompositions = tuple(
        repo.resolve(ForecastUncertaintyDecomposition, i) for i in spec.uncertainty_ids
    )
    require(
        len({d.forecast_id for d in decompositions}) == len(decompositions)
        and all(
            d.forecast_id in spec.forecast_ids
            and d.target_id == spec.target.fingerprint
            and d.horizon_id == spec.target.horizon.fingerprint
            for d in decompositions
        ),
        "exact predeclared uncertainty forecast/target/horizon",
    )
    by_forecast = {d.forecast_id: d for d in decompositions}
    values, policies = [], set()
    for source in sources:
        d = by_forecast.get(source.artifact.fingerprint)
        if d is None:
            return None, "uncertainty-evidence-missing-for-exact-intersection"
        require(
            d.sample_id == source.sample_id and d.origin == source.origin,
            "uncertainty exact sample/full origin",
        )
        kind = (
            UncertaintyType.TOTAL_PREDICTIVE
            if name is StabilityMetricName.PREDICTIVE_VARIANCE
            else UncertaintyType.EXPERT_DISAGREEMENT
            if name is StabilityMetricName.EXPERT_DISAGREEMENT
            else spec.share_component
        )
        c = next((c for c in d.components if c.component is kind), None)
        if c is None or c.value is None or c.measure is not UncertaintyMeasure.VARIANCE:
            return None, "uncertainty-component-not-identifiable-as-variance"
        p = repo.resolve(UncertaintySpec, d.spec_id)
        policies.add(diagnostic_policy_key(repo, p, c))
        value = (
            dict(d.shares).get(kind) if name is StabilityMetricName.COMPONENT_SHARE else c.value
        )
        if value is None:
            return None, "component-share-requires-exact-positive-total-additive-closure"
        values.append(value)
    if len(policies) != 1:
        return None, "uncertainty-policy-method-units-or-identifiability-mismatch"
    return tuple(
        values
    ), "native-uncertainty-identifiability-and-exact-share-semantics-retained"
