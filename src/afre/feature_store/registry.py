"""Immutable version registration; name/version conflicts cannot be overwritten."""

from afre.feature_store.models import RegisteredFeatureDefinition
from afre.feature_store.repository import FeatureStoreRepository


class FeatureRegistry:
    def __init__(self, repository: FeatureStoreRepository) -> None:
        self.repository = repository

    def register_definition(self, feature: RegisteredFeatureDefinition) -> str:
        return self.repository.put(feature)

    def get(self, identity: str) -> RegisteredFeatureDefinition:
        return self.repository.get(RegisteredFeatureDefinition, identity)
