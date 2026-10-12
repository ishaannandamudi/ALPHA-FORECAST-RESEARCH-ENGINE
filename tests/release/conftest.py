"""Reuse the actual native service fixture, copied into isolated databases."""

from tests.service.conftest import service_case, service_template

__all__ = ["service_case", "service_template"]
