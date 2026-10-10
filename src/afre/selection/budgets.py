"""Deterministic exhaustive admission, before any candidate fit."""

from dataclasses import dataclass

from afre.schema import Artifact, contract, require


@contract("sel_budget")
@dataclass(frozen=True, slots=True)
class ResourceBudget(Artifact):
    max_candidates: int
    max_fit_operations: int
    max_train_rows: int
    max_validation_rows: int
    max_numerical_iterations: int
    max_payload_bytes: int

    def _validate(self) -> None:
        require(
            1 <= self.max_candidates <= 128
            and 1 <= self.max_fit_operations <= 4096
            and 1 <= self.max_train_rows <= 256000
            and 1 <= self.max_validation_rows <= 256000
            and 1 <= self.max_numerical_iterations <= 100000000
            and 1 <= self.max_payload_bytes <= 8388608,
            "resource budget bounds",
        )


@contract("sel_usage")
@dataclass(frozen=True, slots=True)
class ResourceUsage(Artifact):
    candidates: int
    fit_operations_reserved: int
    train_rows_reserved: int
    validation_rows_reserved: int
    numerical_iterations_reserved: int
    fit_operations_attempted: int
    fitted_candidates: int
    validation_pairs: int
    payload_bytes: int

    def _validate(self) -> None:
        require(
            all(
                v >= 0
                for v in (
                    self.candidates,
                    self.fit_operations_reserved,
                    self.train_rows_reserved,
                    self.validation_rows_reserved,
                    self.numerical_iterations_reserved,
                    self.fit_operations_attempted,
                    self.fitted_candidates,
                    self.validation_pairs,
                    self.payload_bytes,
                )
            ),
            "nonnegative usage",
        )
        require(
            self.fit_operations_attempted <= self.fit_operations_reserved
            and self.fitted_candidates <= self.candidates
            and self.validation_pairs <= self.validation_rows_reserved,
            "usage within reservations",
        )
