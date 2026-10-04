"""Target-side source freezing, bounded builds and known-by-cutoff queries."""

from afre.datasets import UniverseManifest
from afre.feature_store.models import AvailabilityEvidence
from afre.features import DataQuality, MissingState
from afre.forecast import ForecastOrigin
from afre.ids import InstrumentId
from afre.schema import require
from afre.serialization import canonical_json
from afre.target_engine.builders import build_vintage
from afre.target_engine.corporate_actions import TargetActionStream
from afre.target_engine.definitions import TargetSetManifest
from afre.target_engine.market_data import TargetMarketSource, TargetSourceBuild
from afre.target_engine.models import TargetAudit, TargetDatasetManifest, TargetVintage
from afre.target_engine.repository import TargetRepository
from afre.target_engine.validation import target_known_by_cutoff
from afre.target_engine.windows import TargetCalendar
from afre.time import validate_timestamp


class TargetEngine:
    def __init__(self, repository: TargetRepository) -> None:
        self.repository = repository

    def freeze_source(
        self,
        source: TargetMarketSource,
        calendar: TargetCalendar,
        cutoff_ns: int,
        action_stream: TargetActionStream | None = None,
        benchmark_ids: tuple[str, ...] = (),
    ) -> TargetSourceBuild:
        validate_timestamp(cutoff_ns)
        with self.repository.transaction(), self.repository.validation_cache():
            rows = self.repository._connection.execute(
                (
                    "SELECT fingerprint FROM target_bars WHERE source_id = ? AND "
                    "available_ns <= ? ORDER BY fingerprint LIMIT ?"
                ),
                (
                    source.fingerprint,
                    cutoff_ns,
                    self.repository.target_bounds.source_observations + 1,
                ),
            ).fetchall()
            require(
                len(rows) <= self.repository.target_bounds.source_observations,
                "source observation bound exceeded",
            )
            build = TargetSourceBuild(
                source,
                calendar,
                cutoff_ns,
                tuple(row[0] for row in rows),
                action_stream,
                benchmark_ids,
            )
            self.repository.put(build)
        return build

    def build_dataset(
        self,
        name: str,
        origins: tuple[ForecastOrigin, ...],
        targets: TargetSetManifest,
        source_build_id: str,
        universe: UniverseManifest,
        clocks: AvailabilityEvidence,
    ) -> TargetDatasetManifest:
        bounds = self.repository.target_bounds
        require(0 < len(origins) <= bounds.origins, "target origin bound exceeded")
        require(
            len({origin.instrument for origin in origins}) <= bounds.instruments,
            "target instrument bound exceeded",
        )
        require(
            len(targets.definitions) <= bounds.targets
            and len(origins) * len(targets.definitions) <= bounds.rows,
            "target definition/row bound exceeded",
        )
        require(len(set(origins)) == len(origins), "duplicate target origins")
        with self.repository.transaction(), self.repository.validation_cache():
            build = self.repository.resolve(TargetSourceBuild, source_build_id)
            self.repository.put(universe)
            for definition in targets.definitions:
                self.repository.put(definition)
            self.repository.put(targets)
            rows = []
            for origin in sorted(origins, key=lambda value: value.fingerprint):
                for definition in targets.definitions:
                    value = build_vintage(
                        self.repository,
                        definition,
                        origin,
                        build,
                        clocks,
                        universe.eligible(origin),
                    )
                    self.repository.put(value)
                    rows.append(value.fingerprint)
            manifest = TargetDatasetManifest(
                name,
                origins,
                universe,
                targets,
                source_build_id,
                tuple(rows),
                build.known_as_of_ns,
                clocks.afre_computed_ns,
            )
            self.repository.put(manifest)
        return manifest

    def targets_known_by(
        self,
        cutoff_ns: int,
        targets: TargetSetManifest,
        origins: tuple[ForecastOrigin, ...] = (),
        instruments: tuple[InstrumentId, ...] = (),
        dataset_id: str | None = None,
    ) -> tuple[TargetVintage, ...]:
        validate_timestamp(cutoff_ns)
        bounds = self.repository.target_bounds
        require(
            len(targets.definitions) <= bounds.targets
            and len(origins) <= bounds.origins
            and len(instruments) <= bounds.instruments,
            "target query bounds exceeded",
        )
        definitions = tuple(item.fingerprint for item in targets.definitions)
        sql = "SELECT v.fingerprint FROM target_vintages v "
        args: list[object] = []
        if dataset_id is not None:
            sql += (
                "JOIN target_dataset_rows d ON d.row_id = v.fingerprint AND d.dataset_id = ? "
            )
            args.append(dataset_id)
        sql += (
            f"WHERE v.definition_id IN ({','.join('?' for _ in definitions)}) "
            "AND v.available_ns <= ? AND v.end_ns <= ? AND v.origin_ns < ? "
            "AND v.state = ? AND v.quality = ?"
        )
        args.extend(
            (
                *definitions,
                cutoff_ns,
                cutoff_ns,
                cutoff_ns,
                MissingState.PRESENT.value,
                DataQuality.VERIFIED.value,
            )
        )
        if origins:
            sql += f" AND v.origin_id IN ({','.join('?' for _ in origins)})"
            args.extend(origin.fingerprint for origin in origins)
        if instruments:
            sql += f" AND v.instrument_id IN ({','.join('?' for _ in instruments)})"
            args.extend(item.fingerprint for item in instruments)
        sql += (
            " ORDER BY v.definition_id, v.instrument_id, v.origin_ns, "
            "v.available_ns, v.fingerprint LIMIT ?"
        )
        args.append(bounds.rows + 1)
        with self.repository.read_snapshot():
            if dataset_id is not None:
                manifest = self.repository.get(TargetDatasetManifest, dataset_id)
                require(manifest.targets == targets, "target query dataset/set mismatch")
            indexed = self.repository._connection.execute(sql, args).fetchall()
            require(len(indexed) <= bounds.rows, "target row query bound exceeded")
            values = tuple(self.repository.get(TargetVintage, row[0]) for row in indexed)
            answer = tuple(
                value for value in values if target_known_by_cutoff(value, cutoff_ns)
            )
        require(
            sum(len(canonical_json(value).encode()) for value in answer)
            <= bounds.serialized_bytes,
            "target query serialized byte bound exceeded",
        )
        return answer

    def rows(self, dataset: TargetDatasetManifest) -> tuple[TargetVintage, ...]:
        require(
            len(dataset.row_ids) <= self.repository.target_bounds.rows,
            "target row bound exceeded",
        )
        with self.repository.read_snapshot():
            require(
                self.repository.get(TargetDatasetManifest, dataset.fingerprint) == dataset,
                "target dataset mismatch",
            )
            rows = tuple(
                self.repository.get(TargetVintage, identity) for identity in dataset.row_ids
            )
        require(
            sum(len(canonical_json(row).encode()) for row in rows)
            <= self.repository.target_bounds.serialized_bytes,
            "target row serialized byte bound exceeded",
        )
        return rows

    def audit_target(self, target_id: str) -> TargetAudit:
        with self.repository.read_snapshot():
            value = self.repository.get(TargetVintage, target_id)
            lineage = self.repository.lineage(target_id)
            return TargetAudit(value, tuple(item.fingerprint for item in lineage))

    def audit(self) -> int:
        with self.repository.read_snapshot():
            return self.repository.audit()
