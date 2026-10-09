"""Exact seal uses and same-fold opportunity counts; unknown legacy use stays visible."""

from dataclasses import dataclass

from afre.ids import validate_fingerprint
from afre.multiple_testing.schema import TestReuseStatus, ids
from afre.schema import Artifact, contract, require


@contract("mt_reuse_policy")
@dataclass(frozen=True, slots=True)
class TestReusePolicy(Artifact):
    heavily_reused_count: int
    declared_ns: int

    def _validate(self) -> None:
        require(3 <= self.heavily_reused_count <= 2000, "explicit TEST reuse threshold")


@contract("mt_test_reuse")
@dataclass(frozen=True, slots=True)
class TestReuseDiagnostic(Artifact):
    registry_id: str
    policy_id: str
    trial_id: str
    scope_trial_ids: tuple[str, ...]
    exact_seal_counts: tuple[tuple[str, int], ...]
    untracked_seal_ids: tuple[str, ...]
    use_count: int
    tracked_status: TestReuseStatus
    status: TestReuseStatus
    available_ns: int

    def _normalize(self) -> None:
        ids(self, "scope_trial_ids", "untracked_seal_ids")
        object.__setattr__(self, "exact_seal_counts", tuple(sorted(self.exact_seal_counts)))

    def _validate(self) -> None:
        for identity in (self.registry_id, self.policy_id, self.trial_id):
            validate_fingerprint(identity)
        require(
            self.use_count == len(self.scope_trial_ids) <= 2000
            and len(self.exact_seal_counts) <= 2000
            and all(n >= 1 for _, n in self.exact_seal_counts),
            "TEST reuse count bounds",
        )


def classify_reuse(count: int, heavy: int) -> TestReuseStatus:
    require(
        type(count) is int and type(heavy) is int and 0 <= count <= 2000 and 3 <= heavy <= 2000,
        "TEST reuse bounds",
    )
    return (
        TestReuseStatus.INCOMPATIBLE
        if count == 0
        else TestReuseStatus.FIRST_USE
        if count == 1
        else TestReuseStatus.REUSED
        if count < heavy
        else TestReuseStatus.HEAVILY_REUSED
    )
