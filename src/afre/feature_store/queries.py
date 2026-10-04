"""One indexed selection algorithm for both historical research and serving."""

from afre.feature_store.materialization import FeatureAudit
from afre.feature_store.models import FeatureVintage, RegisteredFeatureDefinition, ScopeBinding
from afre.feature_store.repository import FeatureStoreRepository
from afre.feature_store.schema import QueryPolicy, StoreScope, ValidityRule
from afre.features import MissingState
from afre.forecast import ForecastOrigin
from afre.ids import InstrumentId
from afre.schema import ContractError, require
from afre.serialization import canonical_json


class VintageConflict(ContractError):
    """Equally admissible vintages have no declared precedence."""


def _select_tie(
    repository: FeatureStoreRepository, candidates: tuple[FeatureVintage, ...]
) -> FeatureVintage:
    require(bool(candidates), "empty vintage selection")
    by_id = {item.fingerprint: item for item in candidates}
    superseded: set[str] = set()
    for candidate in candidates:
        current = candidate.predecessor_id
        seen: set[str] = set()
        while current is not None:
            require(current not in seen, "revision lineage cycle")
            require(len(seen) < repository.bounds.lineage_depth, "revision lineage depth bound")
            seen.add(current)
            if current in by_id:
                superseded.add(current)
            current = repository.get(FeatureVintage, current).predecessor_id
    winners = tuple(item for item in candidates if item.fingerprint not in superseded)
    if len(winners) != 1:
        raise VintageConflict(
            "equal-time feature vintages require explicit predecessor precedence"
        )
    return winners[0]


def resolve_entity(
    repository: FeatureStoreRepository,
    feature: RegisteredFeatureDefinition,
    origin: ForecastOrigin,
) -> tuple[InstrumentId | None, str | None]:
    if feature.scope is StoreScope.SECURITY:
        return origin.instrument, None
    rows = repository._connection.execute(
        "SELECT fingerprint FROM fs_bindings WHERE scope = ? AND security_id = ? "
        "AND known_ns <= ? "
        "AND start_ns <= ? AND end_ns > ? ORDER BY known_ns DESC, fingerprint LIMIT ?",
        (
            feature.scope.value,
            origin.instrument.fingerprint,
            origin.availability_cutoff_ns,
            origin.timestamp_ns,
            origin.timestamp_ns,
            repository.bounds.candidates + 1,
        ),
    ).fetchall()
    require(len(rows) <= repository.bounds.candidates, "scope candidate bound exceeded")
    if not rows:
        return None, None
    bindings = tuple(repository.get(ScopeBinding, row[0]) for row in rows)
    latest = max(item.known_ns for item in bindings)
    eligible = tuple(item for item in bindings if item.known_ns == latest)
    if len({item.entity for item in eligible}) != 1:
        raise VintageConflict("ambiguous point-in-time scope mapping")
    return eligible[0].entity, min(item.fingerprint for item in eligible)


def select_as_of(
    repository: FeatureStoreRepository,
    feature: RegisteredFeatureDefinition,
    origin: ForecastOrigin,
    policy: QueryPolicy,
) -> FeatureAudit:
    require(
        repository.get(RegisteredFeatureDefinition, feature.fingerprint) == feature,
        "requested definition is not registered",
    )
    require(feature.build_context == origin.build_context, "forecast/feature build mismatch")
    require(
        feature.adjustment.known_as_of_ns <= origin.availability_cutoff_ns,
        "future feature adjustment policy",
    )
    entity, binding_id = resolve_entity(repository, feature, origin)
    if entity is None:
        return FeatureAudit(
            feature,
            origin,
            MissingState.NOT_APPLICABLE,
            None,
            None,
            "no explicit historical scope binding",
            policy,
        )
    validity = ""
    parameters: list[object] = [
        feature.fingerprint,
        entity.fingerprint,
        origin.availability_cutoff_ns,
    ]
    if feature.validity_rule is not ValidityRule.KNOWN_FACT:
        validity += " AND effective_ns <= ?"
        parameters.append(origin.timestamp_ns)
    if feature.validity_rule is ValidityRule.INTERVAL:
        validity += " AND valid_until_ns > ?"
        parameters.append(origin.timestamp_ns)
    cursor = repository._connection.execute(
        "SELECT fingerprint, available_ns FROM fs_vintages "
        "WHERE definition_id = ? AND entity_id = ? AND available_ns <= ?"
        + validity
        + " ORDER BY available_ns DESC, fingerprint",
        parameters,
    )
    first = cursor.fetchone()
    if first is None:
        return FeatureAudit(
            feature,
            origin,
            MissingState.MISSING,
            None,
            binding_id,
            "no admissible vintage at the cutoff",
            policy,
        )
    candidates = [repository.get(FeatureVintage, first[0])]
    for row in cursor:
        if row[1] != first[1]:
            break
        require(len(candidates) < repository.bounds.candidates, "vintage tie bound exceeded")
        candidates.append(repository.get(FeatureVintage, row[0]))
    vintage = _select_tie(repository, tuple(candidates))
    delivery = vintage.clocks.historical_delivery
    if delivery is not None:
        require(
            delivery.attestor in policy.approved_delivery_attestors,
            "historical delivery attestor is not locally approved",
        )
    state = vintage.state
    if state is MissingState.PRESENT and feature.freshness.stale(
        origin.timestamp_ns,
        vintage.effective_ns,
        vintage.clocks.upstream_available_ns
        if vintage.clocks.upstream_available_ns is not None
        else vintage.clocks.final_available_ns,
    ):
        state = MissingState.STALE
    if vintage.computation_spec_id is not None:
        receipt = repository.receipt_for(vintage.fingerprint)
        require(receipt is not None, "computed vintage has no receipt")
    return FeatureAudit(
        feature,
        origin,
        state,
        vintage,
        binding_id,
        "stale retained value" if state is MissingState.STALE else "latest admissible vintage",
        policy,
    )


def feature_history(
    repository: FeatureStoreRepository,
    feature: RegisteredFeatureDefinition,
    entity: InstrumentId,
    known_as_of_ns: int,
    start_ns: int = 0,
    end_ns: int | None = None,
) -> tuple[FeatureVintage, ...]:
    from afre.time import validate_timestamp

    validate_timestamp(known_as_of_ns)
    validate_timestamp(start_ns)
    endpoint = (2**63 - 1) if end_ns is None else end_ns
    validate_timestamp(endpoint)
    require(start_ns <= endpoint, "reversed history window")
    rows = repository._connection.execute(
        "SELECT fingerprint FROM fs_vintages WHERE definition_id = ? AND entity_id = ? "
        "AND available_ns <= ? AND effective_ns >= ? AND effective_ns <= ? "
        "ORDER BY effective_ns, available_ns, fingerprint LIMIT ?",
        (
            feature.fingerprint,
            entity.fingerprint,
            known_as_of_ns,
            start_ns,
            endpoint,
            repository.bounds.history + 1,
        ),
    ).fetchall()
    require(len(rows) <= repository.bounds.history, "feature history bound exceeded")
    values = tuple(repository.get(FeatureVintage, row[0]) for row in rows)
    require(
        sum(len(canonical_json(value).encode()) for value in values)
        <= repository.bounds.serialized_bytes,
        "history serialized byte bound exceeded",
    )
    return values


def window_history(
    repository: FeatureStoreRepository,
    feature: RegisteredFeatureDefinition,
    entity: InstrumentId,
    origin: ForecastOrigin,
    lookback_ns: int,
    count: int | None,
    policy: QueryPolicy,
) -> tuple[FeatureVintage, ...]:
    # Window is (T-lookback, T]; each effective observation retains its own as-of revision.
    start = max(0, origin.timestamp_ns - lookback_ns + 1)
    history = feature_history(
        repository, feature, entity, origin.availability_cutoff_ns, start, origin.timestamp_ns
    )
    groups: dict[int, list[FeatureVintage]] = {}
    for value in history:
        if value.clocks.historical_delivery is not None:
            require(
                value.clocks.historical_delivery.attestor in policy.approved_delivery_attestors,
                "historical delivery attestor is not locally approved",
            )
        groups.setdefault(value.effective_ns, []).append(value)
    selected: list[FeatureVintage] = []
    for effective_ns in sorted(groups):
        group = groups[effective_ns]
        latest = max(item.clocks.final_available_ns for item in group)
        selected.append(
            _select_tie(
                repository,
                tuple(item for item in group if item.clocks.final_available_ns == latest),
            )
        )
    return tuple(selected[-count:] if count is not None else selected)
