"""One pooled async HTTP client per process, with sane timeouts and retry policy."""

from __future__ import annotations

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from config.env import get_env

_client: httpx.AsyncClient | None = None

USER_AGENT = "spotter-weather-routing/0.1 (assessment; contact via repo)"


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(get_env().http_timeout_s, connect=5.0),
            headers={"User-Agent": USER_AGENT},
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            http2=False,
        )
    return _client


class UpstreamError(RuntimeError):
    """An external provider failed or returned something unusable."""

    def __init__(self, provider: str, message: str, status: int | None = None) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.status = status


def _transient(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return False


def retrying(attempts: int = 3) -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(multiplier=0.5, max=8),
        retry=retry_if_exception(_transient),
        reraise=True,
    )
