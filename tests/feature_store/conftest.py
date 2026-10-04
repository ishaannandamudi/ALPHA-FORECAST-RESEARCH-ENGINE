from collections.abc import Iterator
from pathlib import Path

import pytest

from afre.feature_store import FeatureStore, FeatureStoreRepository
from examples.feature_store_demo import SOURCE, definition


@pytest.fixture
def store(tmp_path: Path) -> Iterator[FeatureStore]:
    with FeatureStoreRepository(tmp_path / "features.sqlite") as repository:
        result = FeatureStore(repository)
        with repository.transaction():
            repository.put(SOURCE)
            result.registry.register_definition(definition())
        yield result
