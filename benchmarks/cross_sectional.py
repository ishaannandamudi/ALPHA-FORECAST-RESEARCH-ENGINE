"""Bounded numerical workload plus separately measured causal SQLite pipeline."""

import json
import math
from dataclasses import replace
from pathlib import Path
from statistics import correlation as oracle_correlation
from tempfile import TemporaryDirectory
from time import perf_counter

from afre.cross_sectional import (
    CrossSectionEngine,
    CrossSectionObservation,
    CrossSectionRepository,
    CrossSectionScoreState,
    NormalizationPolicy,
    PeerTransform,
    RawScore,
)
from afre.cross_sectional.cross_section import ranking_for
from afre.cross_sectional.normalization import peer_state
from afre.cross_sectional.queries import external_as_of
from afre.cross_sectional.ranks import rank_values
from afre.statistical_models.metrics import correlation
from afre.target_engine.models import TargetVintage
from afre.universe.identity import StableSecurityId
from examples.cross_sectional_demo import cross_fixture, group, second_fixture


def main() -> None:
    timings: dict[str, float] = {}
    errors: dict[str, float] = {}
    with TemporaryDirectory() as folder:
        path = Path(folder) / "profile.sqlite"
        start = perf_counter()
        with CrossSectionRepository(path) as repo:
            f = cross_fixture(repo)
            engine = CrossSectionEngine(repo)
            timings["causal_upstream_and_four_security_fixture"] = perf_counter() - start
            # Large workload measures pure numerical components, not PIT universe ingestion.
            synthetic = []
            synthetic_groups = []
            n, origins = 1000, 12
            for i in range(n):
                security = StableSecurityId("profile-security", f"{i:06d}")
                observation = CrossSectionObservation(
                    f.spec.fingerprint,
                    security,
                    replace(f.spec.identity.anchor_origin, instrument=security.instrument),
                    None,
                    None,
                )
                synthetic.append(
                    RawScore(
                        observation.fingerprint,
                        security,
                        float(i),
                        CrossSectionScoreState.AVAILABLE,
                        60,
                        "numeric-profile-only",
                    )
                )
                synthetic_groups.append(group(security, f"group-{i % 20}"))
            raws, groups = tuple(synthetic), tuple(synthetic_groups)
            assert f.spec.group is not None
            vectors = tuple(
                (s.security.fingerprint, s.value) for s in raws if s.value is not None
            )
            start = perf_counter()
            for _ in range(origins):
                rank_values(vectors, f.spec.direction, f.spec.ties)
            timings["synthetic_rank_12_by_1000"] = perf_counter() - start
            start = perf_counter()
            for _ in range(origins):
                z = peer_state(
                    replace(f.spec, normalization=NormalizationPolicy(PeerTransform.ZSCORE)),
                    raws,
                    60,
                )
            timings["synthetic_zscore_12_by_1000"] = perf_counter() - start
            scale = math.sqrt((n * n - 1) / 12)
            errors["mean_std_zscore"] = max(
                abs(v - (i - (n - 1) / 2) / scale)
                for i, raw in enumerate(raws)
                for key, v in z.values
                if key == raw.security.fingerprint
            )
            start = perf_counter()
            robust = peer_state(
                replace(f.spec, normalization=NormalizationPolicy(PeerTransform.MEDIAN_MAD)),
                raws,
                60,
            )
            percentile = peer_state(
                replace(f.spec, normalization=NormalizationPolicy(PeerTransform.PERCENTILE)),
                raws,
                60,
            )
            timings["synthetic_mad_and_percentile_1000"] = perf_counter() - start
            errors["median_mad"] = abs((robust.center or 0) - 499.5) + abs(
                (robust.scale or 0) - 250.0
            )
            pmap = dict(percentile.values)
            errors["percentile"] = max(
                abs(pmap[r.security.fingerprint] - i / (n - 1)) for i, r in enumerate(raws)
            )
            start = perf_counter()
            for _ in range(origins):
                neutral = peer_state(f.spec, raws, 60, groups, True)
            timings["synthetic_group_demean_12_by_1000"] = perf_counter() - start
            nmap = dict(neutral.values)
            errors["group_demean"] = max(
                abs(nmap[r.security.fingerprint] - (i - (i % 20 + 490)))
                for i, r in enumerate(raws)
            )
            x, y = tuple(float(i) for i in range(n)), tuple(float(n - i) for i in range(n))
            start = perf_counter()
            for _ in range(origins):
                ic = correlation(x, y)
            timings["synthetic_ic_12_by_1000"] = perf_counter() - start
            errors["pearson"] = abs((ic.value or 0) - oracle_correlation(x, y))
            start = perf_counter()
            external_as_of(
                repo,
                f.spec.score,
                next(e.security for e in f.ranking.entries if e.rank),
                60,
                60,
            )
            timings["causal_external_lookup"] = perf_counter() - start
            spec = replace(
                f.spec,
                normalization=NormalizationPolicy(PeerTransform.MEDIAN_MAD, mad_scale=1.2345),
            )
            observations = tuple(
                replace(
                    repo.get(CrossSectionObservation, e.observation_id),
                    spec_id=spec.fingerprint,
                )
                for e in f.ranking.entries
            )
            start = perf_counter()
            with repo.read_snapshot(), repo.validation_cache():
                rank, raw, normalized, group_state = ranking_for(repo, spec, observations, 60)
            timings["causal_materialization_including_peer_transforms"] = perf_counter() - start
            start = perf_counter()
            engine._publish(
                (
                    spec.identity,
                    spec,
                    *observations,
                    *raw,
                    normalized,
                    *((group_state,) if group_state else ()),
                    rank,
                )
            )
            timings["causal_atomic_persistence_and_validation"] = perf_counter() - start
            start = perf_counter()
            evaluation = engine.evaluate(
                f.ranking.fingerprint, f.targets, 100, 100, bucket_count=3
            )
            timings["causal_ic_buckets_truth_and_persistence"] = perf_counter() - start
            start = perf_counter()
            second, targets = second_fixture(repo, f)
            engine.evaluate(second.fingerprint, targets, 100, 100)
            stability = engine.stability(f.ranking.fingerprint, second.fingerprint)
            timings["causal_second_origin_stability_and_persistence"] = perf_counter() - start
            errors["spearman_stability"] = abs((stability.spearman.value or 0) + 0.5)
            truth = {
                s: target.value
                for s, i in f.targets
                if i is not None and (target := repo.get(TargetVintage, i)).value is not None
            }
            assert (
                evaluation.top_ids and evaluation.bottom_ids and evaluation.spread is not None
            )
            errors["top_bottom_spread"] = abs(
                evaluation.spread
                - (truth[evaluation.top_ids[0]] - truth[evaluation.bottom_ids[0]])
            )
            start = perf_counter()
            audit = engine.audit_lineage(evaluation.fingerprint)
            timings["causal_bounded_audit_and_persistence"] = perf_counter() - start
            counts = {
                "synthetic_security_origins": n * origins,
                "synthetic_securities_per_section": n,
                "synthetic_groups": 20,
                "causal_eligible": 4,
                "causal_ranked": 3,
                "causal_origins": 2,
                "causal_audit_nodes": len(audit.evidence_ids),
                "cs_artifacts": repo._connection.execute(
                    "SELECT count(*) FROM cs_artifacts"
                ).fetchone()[0],
            }
        start = perf_counter()
        with CrossSectionRepository(path) as repo:
            repo.audit()
        timings["restart_and_full_registry_audit"] = perf_counter() - start
        result = {
            "engine": "0.10.0",
            "store": "1.9",
            "sqlite_version": 10,
            "scope": "large pure numerical components; separate small causal pipeline",
            "counts": counts,
            "seconds": timings,
            "maximum_numerical_errors": errors,
            "max_error": max(errors.values()),
            "storage_bytes": path.stat().st_size,
            "production_sla": False,
        }
        print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
