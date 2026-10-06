"""Additive immutable sequence storage and exact prior layout expectations."""

from afre.calibration.storage import calibration_schema
from afre.cross_sectional.storage import cross_section_schema
from afre.event_conditioned.storage import event_schema
from afre.feature_store.repository import feature_store_schema
from afre.mixture.storage import mixture_schema
from afre.multihorizon.storage import multihorizon_schema
from afre.nonlinear.storage import nonlinear_schema
from afre.persistence import _schema_statements
from afre.probabilistic.storage import probabilistic_schema
from afre.regime_conditioned.storage import regime_schema
from afre.research_datasets.storage import dataset_schema
from afre.schema import Artifact
from afre.statistical_models.storage import model_schema
from afre.target_engine.repository import target_schema
from afre.universe.repository import universe_schema

METADATA = {
    "schema_version": "1.0",
    "engine_version": "0.1.0",
    "store_schema_version": "1.1",
    "feature_store_schema": "1.0",
    "feature_store_engine_version": "0.2.0",
    "target_store_schema_version": "1.2",
    "target_schema": "1.0",
    "target_engine_version": "0.3.0",
    "universe_store_schema_version": "1.3",
    "universe_schema": "1.0",
    "universe_engine_version": "0.4.0",
    "research_store_schema_version": "1.4",
    "dataset_schema": "1.0",
    "research_engine_version": "0.5.0",
    "model_store_schema_version": "1.5",
    "model_schema": "1.0",
    "model_engine_version": "0.6.0",
    "probabilistic_store_schema_version": "1.6",
    "probabilistic_schema": "1.0",
    "probabilistic_engine_version": "0.7.0",
    "calibration_store_schema_version": "1.7",
    "calibration_schema": "1.0",
    "calibration_engine_version": "0.8.0",
    "multihorizon_store_schema_version": "1.8",
    "multihorizon_schema": "1.0",
    "multihorizon_engine_version": "0.9.0",
    "cross_sectional_store_schema_version": "1.9",
    "cross_sectional_schema": "1.0",
    "cross_sectional_engine_version": "0.10.0",
    "event_store_schema_version": "1.10",
    "event_conditioned_schema": "1.0",
    "event_conditioned_engine_version": "0.11.0",
    "regime_store_schema_version": "1.11",
    "regime_conditioned_schema": "1.0",
    "regime_conditioned_engine_version": "0.12.0",
    "mixture_store_schema_version": "1.12",
    "mixture_schema": "1.0",
    "mixture_engine_version": "0.13.0",
    "nonlinear_store_schema_version": "1.13",
    "nonlinear_schema": "1.0",
    "nonlinear_engine_version": "0.14.0",
    "sequence_store_schema_version": "1.14",
    "sequence_schema": "1.0",
    "sequence_engine_version": "0.15.0",
}


def all_statements() -> tuple[str, ...]:
    return (
        *_schema_statements(),
        *feature_store_schema(),
        *target_schema(),
        *universe_schema(),
        *dataset_schema(),
        *model_schema(),
        *probabilistic_schema(),
        *calibration_schema(),
        *multihorizon_schema(),
        *cross_section_schema(),
        *event_schema(),
        *regime_schema(),
        *mixture_schema(),
        *nonlinear_schema(),
        *sequence_schema(),
    )


def sequence_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE sq_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT NOT NULL)"
        ),
        (
            "CREATE TABLE sq_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "feature_id TEXT, source_id TEXT, window_id TEXT, security_id TEXT, "
            "origin_ns INTEGER, target_id TEXT, horizon_id TEXT, family TEXT, model_id TEXT, "
            "spec_id TEXT, available_ns INTEGER, cutoff_ns INTEGER, test_id TEXT, "
            "afre_ready_ns INTEGER)"
        ),
        (
            "CREATE TABLE sq_links (fingerprint TEXT NOT NULL, reference_id TEXT NOT NULL, "
            "PRIMARY KEY (fingerprint, reference_id))"
        ),
        "CREATE INDEX sq_feature_idx ON sq_records (feature_id, source_id, available_ns)",
        "CREATE INDEX sq_window_idx ON sq_records (window_id, security_id, origin_ns)",
        "CREATE INDEX sq_target_idx ON sq_records (target_id, horizon_id, family)",
        "CREATE INDEX sq_model_idx ON sq_records (model_id, spec_id, available_ns)",
        "CREATE INDEX sq_evaluation_idx ON sq_records (model_id, cutoff_ns, test_id)",
        "CREATE INDEX sq_reference_idx ON sq_links (reference_id, fingerprint)",
    ]
    for table in ("sq_artifacts", "sq_records"):
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} WHEN "
            f"EXISTS (SELECT 1 FROM {table} WHERE fingerprint=NEW.fingerprint) "
            "BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
        )
    for table in ("sq_artifacts", "sq_records", "sq_links"):
        for operation in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{operation.lower()} BEFORE {operation} "
                f"ON {table} BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def sequence_index(value: Artifact) -> tuple[object, ...]:
    from afre.sequence.artifacts import (
        SequenceDataset,
        SequenceEvaluation,
        SequenceForecast,
        SequenceModelArtifact,
        SequenceObservation,
        SequenceSnapshot,
        SequenceTransformArtifact,
    )
    from afre.sequence.definitions import SequenceFeatureDefinition, SequenceModelSpec

    feature = source = window = security = origin = target = horizon = family = model = spec = (
        available
    ) = cutoff = test = None
    if isinstance(value, SequenceFeatureDefinition):
        feature, source = value.fingerprint, value.source_definition_id
    elif isinstance(value, SequenceObservation):
        feature, source, security, origin, available = (
            value.feature_id,
            value.source_id,
            value.security.fingerprint,
            value.observation_ns,
            value.available_ns,
        )
    elif isinstance(value, SequenceSnapshot):
        window, security, origin, available = (
            value.window_id,
            value.origin.instrument.fingerprint,
            value.origin.timestamp_ns,
            value.available_ns,
        )
    elif isinstance(value, SequenceModelSpec):
        spec, window, target, horizon, family, cutoff = (
            value.fingerprint,
            value.window.fingerprint,
            value.target.fingerprint,
            value.target.horizon.fingerprint,
            value.family.value,
            value.cutoff_ns,
        )
    elif isinstance(value, SequenceModelArtifact):
        model, spec, family, available, cutoff = (
            value.fingerprint,
            value.spec_id,
            value.family.value,
            value.available_ns,
            value.cutoff_ns,
        )
    elif isinstance(value, SequenceForecast):
        model, spec, security, origin, target, available = (
            value.model_id,
            value.spec_id,
            value.security.instrument.fingerprint,
            value.origin.timestamp_ns,
            value.target_definition_id,
            value.available_ns,
        )
    elif isinstance(value, SequenceEvaluation):
        model, cutoff, available, test = (
            value.model_id,
            value.cutoff_ns,
            value.available_ns,
            value.test_evaluation_id,
        )
    elif isinstance(value, SequenceDataset):
        spec, target, horizon, cutoff, available = (
            value.spec_id,
            value.target_id,
            value.horizon_id,
            value.cutoff_ns,
            value.computed_ns,
        )
    elif isinstance(value, SequenceTransformArtifact):
        spec, cutoff, available = value.spec_id, value.cutoff_ns, value.available_ns
    ready = value.afre_ready_ns if isinstance(value, SequenceObservation) else None
    return (
        value.fingerprint,
        feature,
        source,
        window,
        security,
        origin,
        target,
        horizon,
        family,
        model,
        spec,
        available,
        cutoff,
        test,
        ready,
    )
