"""Frozen PIT feature selection reuses AFRE-1 precedence and freshness contracts."""

from afre.feature_store.models import FeatureVintage, RegisteredFeatureDefinition
from afre.feature_store.queries import _select_tie
from afre.features import DataQuality, MissingState
from afre.schema import require
from afre.universe.identity import StableSecurityId
from afre.universe.models import UniverseInputBuild
from afre.universe.repository import UniverseRepository


def observations(
    repository: UniverseRepository,
    build_id: str,
    feature: RegisteredFeatureDefinition,
    security: StableSecurityId,
    at_ns: int,
    start_ns: int = 0,
) -> tuple[FeatureVintage, ...]:
    build = repository.resolve(UniverseInputBuild, build_id)
    cutoff = min(at_ns, build.known_as_of_ns)
    require(feature.adjustment.known_as_of_ns <= cutoff, "future feature adjustment policy")
    rows = repository._connection.execute(
        (
            "SELECT v.fingerprint FROM fs_vintages v JOIN u_build_features b ON "
            "b.vintage_id=v.fingerprint AND b.build_id=? WHERE v.definition_id=? "
            "AND v.entity_id=? AND v.effective_ns>=? AND v.effective_ns<=? AND "
            "v.available_ns<=? ORDER BY "
            "v.effective_ns,v.available_ns,v.fingerprint LIMIT ?"
        ),
        (
            build_id,
            feature.fingerprint,
            security.instrument.fingerprint,
            start_ns,
            at_ns,
            cutoff,
            repository.universe_bounds.vintages + 1,
        ),
    ).fetchall()
    require(len(rows) <= repository.universe_bounds.vintages, "eligibility observation bound")
    grouped: dict[int, list[FeatureVintage]] = {}
    for row in rows:
        value = repository.resolve(FeatureVintage, row[0])
        require(
            value.feature == feature and value.entity == security.instrument,
            "eligibility feature/security mismatch",
        )
        repository.approved(
            value.clocks.historical_delivery, build.query_policy.approved_delivery_attestors
        )
        grouped.setdefault(value.effective_ns, []).append(value)
    result = []
    for at in sorted(grouped):
        group = grouped[at]
        latest = max(value.clocks.final_available_ns for value in group)
        result.append(
            _select_tie(
                repository,
                tuple(value for value in group if value.clocks.final_available_ns == latest),
            )
        )
    return tuple(result)


def usable(value: FeatureVintage, at_ns: int) -> bool:
    return (
        value.state is MissingState.PRESENT
        and value.quality is DataQuality.VERIFIED
        and type(value.value) in (int, float)
        and not value.feature.freshness.stale(
            at_ns,
            value.effective_ns,
            value.clocks.upstream_available_ns
            if value.clocks.upstream_available_ns is not None
            else value.clocks.final_available_ns,
        )
    )
