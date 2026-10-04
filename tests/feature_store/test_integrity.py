"""Cross-artifact integrity, immutable logic, true joins and transitive audit evidence."""

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from afre.feature_store import (
    FeatureSetManifest,
    FeatureStore,
    FeatureStoreRepository,
    NormalizationSpec,
    NormalizationState,
    RegisteredFeatureDefinition,
)
from afre.feature_store.dag import MissingInputPolicy, Transformation
from afre.feature_store.materialization import FeatureAudit
from afre.feature_store.normalization import NormalizationMethod
from afre.feature_store.queries import select_as_of
from afre.feature_store.schema import QueryBounds, QueryPolicy, ValidityRule
from afre.features import DataQuality, MissingState
from afre.forecast import ForecastOrigin
from afre.lineage import Parameter
from afre.schema import ContractError
from afre.serialization import canonical_json
from examples.feature_store_demo import (
    INPUT_ID,
    SOURCE,
    clocks,
    computation,
    dataset,
    definition,
    origin,
    populate,
    source_vintage,
)
from tests.feature_store.test_queries import append


def test_changed_computation_logic_requires_definition_revision(store: FeatureStore) -> None:
    raw = definition()
    derived = definition("market.immutable_logic", "currency", (raw,))
    spec = computation(derived, (raw,), Transformation.IDENTITY)
    append(store, derived, source_vintage(raw, 1, 2), spec)
    for changed in (
        replace(spec, minimum_observations=2),
        replace(spec, missing_input_policy=MissingInputPolicy.PROPAGATE),
        replace(spec, implementation_version="new-implementation"),
    ):
        with pytest.raises(ContractError, match="new definition revision"):
            append(store, changed)
    revised = replace(derived, definition=replace(derived.definition, version="2"))
    append(store, revised, replace(spec, output=revised, minimum_observations=2))
    assert revised.fingerprint != derived.fingerprint
    store.audit()


def test_insertion_and_origin_order_replay(tmp_path: Path) -> None:
    features = FeatureSetManifest((definition(), definition("market.volume", "shares")))
    manifest = dataset(features)
    values = tuple(
        source_vintage(feature, effective, effective + 1, float(effective))
        for feature in features.definitions
        for effective in (1, 3, 5)
    )
    payloads = []
    for index, sequence in enumerate((values, tuple(reversed(values)))):
        with FeatureStoreRepository(tmp_path / f"order-{index}.sqlite") as repository:
            store = FeatureStore(repository)
            append(store, SOURCE, *features.definitions, *sequence)
            origins = (origin(2), origin(4), origin(6))
            materialized = store.materialize(
                origins if index == 0 else tuple(reversed(origins)), manifest, features, 7
            )
            payloads.append(canonical_json(materialized))
    assert payloads[0] == payloads[1]


def test_ancestor_target_corruption_rejects_transitive_computation(
    store: FeatureStore, tmp_path: Path
) -> None:
    raw = definition()
    child_source = replace(
        SOURCE,
        provenance=replace(SOURCE.provenance, artifact_id="child"),
        parent_source_ids=(SOURCE.fingerprint,),
    )
    intermediate = definition("market.intermediate", "currency", (raw,))
    final = definition("market.final", "currency", (intermediate,))
    append(
        store, child_source, intermediate, final, source_vintage(raw, 1, 2, source=child_source)
    )
    store.compute(
        computation(intermediate, (raw,), Transformation.IDENTITY), origin(3), clocks(3)
    )
    path = tmp_path / "features.sqlite"
    with sqlite3.connect(path) as connection:
        payload = json.loads(canonical_json(SOURCE))
        payload["artifact"]["fields"]["provenance"]["fields"]["artifact_id"] = (
            "afre.target_row:1.0:" + "a" * 64
        )
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'immutable_fs_artifacts_update'"
        ).fetchone()[0]
        connection.execute("DROP TRIGGER immutable_fs_artifacts_update")
        connection.execute(
            "UPDATE fs_artifacts SET payload = ? WHERE fingerprint = ?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), SOURCE.fingerprint),
        )
        connection.execute(trigger)
    with pytest.raises(ContractError, match="target/evaluation"):
        store.compute(
            computation(final, (intermediate,), Transformation.IDENTITY), origin(4), clocks(4)
        )
    with pytest.raises(ContractError):
        store.audit()


def test_actual_batch_join_pins_snapshot_across_insertions(
    store: FeatureStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import afre.feature_store.engine as module

    feature = definition()
    features = FeatureSetManifest((feature,))
    before = source_vintage(feature, 1, 2, 10.0)
    inserted = source_vintage(feature, 2, 3, 20.0)
    append(store, before)
    original = select_as_of
    calls = 0
    with FeatureStoreRepository(tmp_path / "features.sqlite") as writer:

        def interleave(
            repository: FeatureStoreRepository,
            feature: RegisteredFeatureDefinition,
            at: ForecastOrigin,
            policy: QueryPolicy,
        ) -> FeatureAudit:
            nonlocal calls
            result = original(repository, feature, at, policy)
            calls += 1
            if calls == 1:
                with writer.transaction():
                    writer.put(inserted)
            return result

        monkeypatch.setattr(module, "select_as_of", interleave)
        results = store.point_in_time_join((origin(3), origin(4)), dataset(features), features)
        assert all(item.audits[0].selected == before for item in results)
    monkeypatch.setattr(module, "select_as_of", original)
    assert store.feature_as_of(feature, origin(3)).selected == inserted


def test_bad_fit_quality_and_missing_samples_rejected(store: FeatureStore) -> None:
    raw = definition()
    value = source_vintage(raw, 1, 2)
    invalids = (
        replace(value, value=None, state=MissingState.MISSING),
        replace(value, quality=DataQuality.UNVERIFIED),
    )
    spec = NormalizationSpec(raw, NormalizationMethod.STANDARDIZE, "supplied-v1")
    append(store, spec, *invalids)
    for sample in invalids:
        state = NormalizationState(
            spec,
            (sample.fingerprint,),
            3,
            4,
            (Parameter("mean", 0.0), Parameter("stddev", 1.0)),
            INPUT_ID,
        )
        with pytest.raises(ContractError, match="absent or unverified"):
            append(store, state)


def test_revision_cross_entity_future_and_different_observation_rejected(
    store: FeatureStore,
) -> None:
    from afre.ids import InstrumentId

    raw = definition()
    base = source_vintage(raw, 5, 10)
    append(store, base)
    for revised in (
        replace(base, clocks=clocks(9), predecessor_id=base.fingerprint),
        replace(
            base, entity=InstrumentId("security", "other"), predecessor_id=base.fingerprint
        ),
        replace(base, effective_ns=6, predecessor_id=base.fingerprint),
    ):
        with pytest.raises(ContractError, match="revision predecessor"):
            append(store, revised)


def test_audit_cannot_claim_different_row_or_state(store: FeatureStore) -> None:
    raw = definition()
    append(store, source_vintage(raw, 1, 2))
    features = FeatureSetManifest((raw,))
    result = store.point_in_time_join((origin(3),), dataset(features), features)[0]
    with pytest.raises(ContractError, match="audit state"):
        replace(result.audits[0], state=MissingState.MISSING)
    with pytest.raises(ContractError, match="audited exact vintage"):
        replace(
            result,
            row=replace(result.row, features=(replace(result.row.features[0], value=999.0),)),
        )
    with pytest.raises(ContractError, match="duplicate"):
        from afre.feature_store import FeatureMaterialization

        FeatureMaterialization((result, result), 4, "v1")


def test_market_lineage_retains_exact_completed_bar(tmp_path: Path) -> None:
    from afre.feature_store.providers import MarketBar

    with FeatureStoreRepository(tmp_path / "demo.sqlite") as repository:
        store, features = populate(repository)
        raw = next(
            item for item in features.definitions if item.definition.name == "market.close"
        )
        selected = store.feature_as_of(raw, origin(181_000_000_000)).selected
        assert selected is not None
        lineage = store.lineage(selected.fingerprint)
        assert any(isinstance(item, MarketBar) for item in lineage)


def test_known_future_fact_history_and_query_byte_bound(store: FeatureStore) -> None:
    feature = replace(
        definition(),
        definition=replace(definition().definition, name="market.fact"),
        validity_rule=ValidityRule.KNOWN_FACT,
    )
    append(store, feature, source_vintage(feature, 50, 2))
    history = store.feature_history(feature, origin(3).instrument, 3)
    assert history[0].effective_ns == 50
    normal = store.feature_as_of(feature, origin(3))
    assert normal.selected is not None
    store.repository.bounds = QueryBounds(
        serialized_bytes=len(canonical_json(normal.selected).encode()) + 10
    )
    with pytest.raises(ContractError, match="query serialized"):
        store.feature_as_of(feature, origin(3))


def test_persisted_audits_sets_and_receipts_resolve_exact_links(store: FeatureStore) -> None:
    from afre.feature_store import ScopeBinding
    from afre.feature_store.materialization import FeatureAudit
    from afre.feature_store.schema import StoreScope
    from afre.features import FeatureScope
    from afre.ids import InstrumentId
    from afre.time import TimeRange

    raw = definition()
    derived = definition("market.persisted", "currency", (raw,))
    append(store, derived, source_vintage(raw, 1, 2))
    _, receipt = store.compute(
        computation(derived, (raw,), Transformation.IDENTITY), origin(3), clocks(3)
    )
    with pytest.raises(ContractError):
        replace(receipt, computation_available_ns=2)
    with pytest.raises(ContractError):
        append(store, replace(receipt, origin=origin(2)))
    audit = store.feature_as_of(raw, origin(3))
    append(store, audit)
    append(store, store.feature_as_of(raw, origin(0)))
    unknown = definition("market.unregistered")
    with pytest.raises(KeyError):
        append(store, FeatureSetManifest((unknown,)))
    with pytest.raises(ContractError):
        replace(audit, origin=origin(3, InstrumentId("security", "other")))
    issuer = replace(
        raw,
        definition=replace(
            raw.definition, name="market.issuer_audit", scope=FeatureScope.ENTITY
        ),
        scope=StoreScope.ISSUER,
    )
    entity = InstrumentId("issuer", "0001")
    binding = ScopeBinding(
        StoreScope.ISSUER, entity, origin(3).instrument, TimeRange(0, 10), 2, SOURCE.provenance
    )
    append(store, issuer, binding, source_vintage(issuer, 1, 2, entity=entity))
    broadcast = store.feature_as_of(issuer, origin(3))
    append(store, broadcast)
    with pytest.raises(ContractError, match="binding"):
        replace(broadcast, scope_binding_id=None)
    with pytest.raises(ContractError):
        FeatureAudit(raw, origin(3), MissingState.PRESENT, None, None, "fake", store.policy)
    store.audit()


def test_qualified_materialization_preserves_later_creation(store: FeatureStore) -> None:
    from afre.feature_store import FeatureMaterialization
    from afre.feature_store.schema import QueryPolicy
    from tests.feature_store.test_availability import MINUTE, TEN, qualified

    allowed = FeatureStore(store.repository, QueryPolicy(("archive-audit-v1",)))
    raw = definition()
    value = replace(source_vintage(raw, TEN, TEN + 2 * MINUTE), clocks=qualified())
    with store.repository.transaction():
        allowed.append_vintage(value)
    features = FeatureSetManifest((raw,))
    results = allowed.point_in_time_join(
        (origin(TEN + 2 * MINUTE),), dataset(features), features
    )
    with pytest.raises(ContractError, match="physical reconstruction"):
        FeatureMaterialization(results, TEN + 2 * MINUTE, "v1")
    materialized = allowed.materialize(
        (origin(TEN + 2 * MINUTE),), dataset(features), features, value.clocks.afre_computed_ns
    )
    assert materialized.results[0].audits[0].selected == value
    assert materialized.created_ns > materialized.results[0].row.origin.timestamp_ns
