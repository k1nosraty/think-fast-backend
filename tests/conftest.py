import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def isolate_cache() -> None:
    cache.clear()
