from collections.abc import Iterator
from pathlib import Path

import pytest
from django.core.cache import cache

import providers.http
import providers.jev
from config.env import get_env


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
    monkeypatch.setattr(providers.jev, "client", lambda: None)


@pytest.fixture(autouse=True)
def _no_local_data(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Tests never read the forecast copy or zone outlines a local worker downloaded."""
    monkeypatch.setattr(get_env(), "data_dir", tmp_path)
