"""Additive immutable registry with fully checked relational projections."""

from afre.cross_sectional.artifacts import (
    CrossSectionEvaluation,
    CrossSectionObservation,
    CrossSectionRanking,
    CrossSectionTruth,
    RawScore,
)
from afre.cross_sectional.definitions import CrossSectionIdentity, CrossSectionSpec
from afre.cross_sectional.external import ExternalSignal
from afre.cross_sectional.groups import GroupMembership
from afre.cross_sectional.models import CrossSectionModel
from afre.schema import Artifact


def cross_section_schema() -> tuple[str, ...]:
    statements = [
        (
            "CREATE TABLE cs_artifacts (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "type_name TEXT NOT NULL, schema_version TEXT NOT NULL, payload TEXT "
            "NOT NULL)"
        ),
        (
            "CREATE TABLE cs_records (fingerprint TEXT PRIMARY KEY NOT NULL, "
            "origin_ns INTEGER, target_id TEXT, horizon_id TEXT, universe_id TEXT, "
            "security_id TEXT, group_id TEXT, score_source TEXT, provider TEXT, "
            "model_id TEXT, ranking_id TEXT, cutoff_ns INTEGER, available_ns "
            "INTEGER)"
        ),
        (
            "CREATE TABLE cs_members (fingerprint TEXT NOT NULL, security_id TEXT "
            "NOT NULL, source_id TEXT, group_id TEXT, PRIMARY KEY (fingerprint, "
            "security_id))"
        ),
        (
            "CREATE INDEX cs_origin_idx ON cs_records (origin_ns, universe_id, "
            "target_id, horizon_id)"
        ),
        "CREATE INDEX cs_security_idx ON cs_records (security_id, available_ns)",
        "CREATE INDEX cs_group_idx ON cs_records (group_id, provider, origin_ns, available_ns)",
        (
            "CREATE INDEX cs_provider_idx ON cs_records (provider, score_source, "
            "security_id, origin_ns, available_ns)"
        ),
        "CREATE INDEX cs_model_idx ON cs_records (model_id, cutoff_ns, available_ns)",
        "CREATE INDEX cs_rank_idx ON cs_records (ranking_id, cutoff_ns, available_ns)",
        "CREATE INDEX cs_member_idx ON cs_members (security_id, group_id, source_id)",
    ]
    for table in ("cs_artifacts", "cs_records", "cs_members"):
        key = "fingerprint=NEW.fingerprint" + (
            " AND security_id=NEW.security_id" if table == "cs_members" else ""
        )
        statements.append(
            f"CREATE TRIGGER immutable_{table}_insert BEFORE INSERT ON {table} WHEN "
            f"EXISTS (SELECT 1 FROM {table} WHERE {key}) BEGIN SELECT RAISE(ABORT, "
            f"'immutable AFRE artifact'); END"
        )
        for op in ("UPDATE", "DELETE"):
            statements.append(
                f"CREATE TRIGGER immutable_{table}_{op.lower()} BEFORE {op} ON {table} "
                f"BEGIN SELECT RAISE(ABORT, 'immutable AFRE artifact'); END"
            )
    return tuple(statements)


def cross_section_indexes(
    value: Artifact, identity: str
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    origin = target = horizon = universe = security = group = score = provider = model = (
        ranking
    ) = cutoff = available = None
    members: list[tuple[object, ...]] = []
    if isinstance(value, (CrossSectionIdentity, CrossSectionSpec)):
        c = value.identity if isinstance(value, CrossSectionSpec) else value
        origin, cutoff = c.anchor_origin.timestamp_ns, c.anchor_origin.availability_cutoff_ns
        target, horizon, universe = (
            c.target.fingerprint,
            c.target.horizon.fingerprint,
            c.snapshot_id,
        )
        if isinstance(value, CrossSectionSpec):
            score, provider, model = (
                value.score.source.value,
                value.score.provider_name,
                value.score.model_id,
            )
    elif isinstance(value, CrossSectionObservation):
        security, origin, cutoff = (
            value.security.fingerprint,
            value.origin.timestamp_ns,
            value.origin.availability_cutoff_ns,
        )
        universe, group = value.origin.universe_id, value.group_id
        members.append((identity, security, value.source_id, value.group_id))
    elif isinstance(value, ExternalSignal):
        origin, available, security = (
            value.as_of_ns,
            value.clocks.final_available_ns,
            value.security.fingerprint,
        )
        provider, score = value.provider_name, value.signal_name
    elif isinstance(value, GroupMembership):
        origin, available, security = (
            value.validity.start_ns,
            value.clocks.final_available_ns,
            value.security.fingerprint,
        )
        group, provider = value.group_id, value.provider
    elif isinstance(value, RawScore):
        security, available = value.security.fingerprint, value.available_ns
    elif isinstance(value, CrossSectionRanking):
        ranking, available, origin = identity, value.available_ns, value.computed_ns
        members = [
            (identity, e.security.fingerprint, e.raw_id, value.group_neutral_id)
            for e in value.entries
        ]
    elif isinstance(value, CrossSectionTruth):
        ranking, cutoff, available = value.ranking_id, value.cutoff_ns, value.available_ns
        members = [
            (identity, r.security.fingerprint, r.target_id, r.sample_id) for r in value.rows
        ]
    elif isinstance(value, CrossSectionEvaluation):
        ranking, cutoff, available = value.ranking_id, value.cutoff_ns, value.available_ns
    elif isinstance(value, CrossSectionModel):
        model, cutoff, available = value.spec_id, value.cutoff_ns, value.available_ns
    return (
        (
            "cs_records",
            (
                identity,
                origin,
                target,
                horizon,
                universe,
                security,
                group,
                score,
                provider,
                model,
                ranking,
                cutoff,
                available,
            ),
        ),
        *(("cs_members", row) for row in sorted(members)),
    )
