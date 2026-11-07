from collections.abc import Iterator

import pytest
from django.core.cache import cache

import providers.http
import providers.jev


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    """Fresh HTTP client (bound to each test's event loop) and an empty cache per test."""
    providers.http._client = None
    cache.clear()
    yield
    providers.http._client = None


@pytest.fixture(autouse=True)
def _no_jev(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never call the real Jev API; triage falls back to the keyword rules unless a test fakes it."""
    monkeypatch.setattr(providers.jev, "_client", lambda: None)
