"""A second writer cannot change a ranking's open snapshot or pinned upstream bytes."""

from dataclasses import replace

from afre.cross_sectional import CrossSectionEngine, CrossSectionRepository
from afre.cross_sectional.queries import group_as_of
from afre.serialization import canonical_json
from afre.target_engine.models import TargetVintage
from afre.universe.membership import UniverseMembershipVintage
from afre.universe.schema import MembershipState
from examples.cross_sectional_demo import external, group
from examples.feature_store_demo import clocks
from tests.cross_sectional.conftest import Case


def test_concurrent_universe_group_target_external_corrections(case: Case) -> None:
    f = case.fixture
    security = next(e.security for e in f.ranking.entries if e.rank is not None)
    target = case.repo.get(
        TargetVintage, next(i for s, i in f.targets if s == security.fingerprint) or ""
    )
    row = case.repo._connection.execute(
        "SELECT fingerprint FROM u_records WHERE type_name='UniverseMembershipVintage' "
        "AND security_id=? AND start_ns=0",
        (security.instrument.fingerprint,),
    ).fetchone()
    original = case.repo.get(UniverseMembershipVintage, row[0])
    with CrossSectionRepository(case.path) as writer:

        def concurrent_insert() -> None:
            before = {
                table: case.repo._connection.execute(
                    f"SELECT count(*) FROM {table}"
                ).fetchone()[0]
                for table in ("u_artifacts", "target_artifacts", "cs_artifacts")
            }
            other = CrossSectionEngine(writer)
            other.publish_group(group(security, "corrected-sector", 90))
            other.publish_external(external(security, 60, 99.0, 90))
            with writer.transaction():
                writer.put(replace(target, clocks=clocks(110)))
                writer.put(
                    replace(
                        original,
                        state=MembershipState.EXCLUDED,
                        evidence=replace(
                            original.evidence,
                            clocks=clocks(90),
                            predecessor_id=original.fingerprint,
                        ),
                    )
                )
            after = {
                table: case.repo._connection.execute(
                    f"SELECT count(*) FROM {table}"
                ).fetchone()[0]
                for table in before
            }
            assert before == after
            assert f.spec.group is not None
            selected = group_as_of(case.repo, f.spec.group, security, 60, 100)
            assert selected is not None and selected.group_id != "corrected-sector"

        rank = case.engine.build_ranking(
            f.spec, f.sources, f.group_refs, snapshot_hook=concurrent_insert
        )
    assert rank == f.ranking
    assert f.spec.group is not None
    selected = group_as_of(case.repo, f.spec.group, security, 60, 100)
    assert selected is not None and selected.group_id == "corrected-sector"
    assert canonical_json(case.repo.get(type(rank), rank.fingerprint)) == canonical_json(
        f.ranking
    )


def test_corrected_source_new_identity_old_bytes(case: Case) -> None:
    f = case.fixture
    security = next(e.security for e in f.ranking.entries if e.rank is not None)
    new = case.engine.publish_external(external(security, 60, 99.0))
    sources = tuple((s, new if s == security.fingerprint else i) for s, i in f.sources)
    corrected = case.engine.build_ranking(f.spec, sources, f.group_refs)
    assert corrected.fingerprint != f.ranking.fingerprint
    old_eval = case.engine.evaluate(f.ranking.fingerprint, f.targets, 100, 100)
    new_eval = case.engine.evaluate(corrected.fingerprint, f.targets, 100, 100)
    assert old_eval.fingerprint != new_eval.fingerprint
    assert canonical_json(
        case.repo.get(type(f.ranking), f.ranking.fingerprint)
    ) == canonical_json(f.ranking)
