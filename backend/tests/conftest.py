from collections.abc import Iterator

import pytest
from django.core.cache import cache

import providers.http


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    """Fresh HTTP client (bound to each test's event loop) and an empty cache per test."""
    providers.http._client = None
    cache.clear()
    yield
    providers.http._client = None
