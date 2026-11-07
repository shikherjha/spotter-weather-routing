"""The one HTTP client all providers share, and how upstream failures surface.

Every provider call goes through `fetch`, which retries transient failures and turns anything
else into an `UpstreamError`. Errors never carry the request URL: API keys travel in query
strings, and httpx puts the full URL in its exception text.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import AsyncRetrying, retry_if_exception, stop_after_attempt, wait_exponential_jitter

from config.env import get_env

USER_AGENT = "spotter-weather-routing/0.1 (+https://github.com/shikherjha/spotter-weather-routing)"
RETRYABLE = frozenset({429, 500, 502, 503, 504})

_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(get_env().http_timeout_s, connect=5.0),
            headers={"User-Agent": USER_AGENT},
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
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
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in RETRYABLE


def retrying(attempts: int = 3) -> AsyncRetrying:
    return AsyncRetrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(multiplier=0.5, max=8),
        retry=retry_if_exception(_transient),
        reraise=True,
    )


async def fetch(provider: str, method: str, url: str, *, attempts: int = 3, **kwargs: Any) -> httpx.Response:
    """Send a request, retrying 429/5xx and connection errors.

    Returns the response for any other status, so callers can read a 4xx body; raises
    `UpstreamError` (without the URL) once retries run out.
    """
    try:
        async for attempt in retrying(attempts):
            with attempt:
                resp = await client().request(method, url, **kwargs)
                if resp.status_code in RETRYABLE:
                    resp.raise_for_status()
                return resp
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        raise UpstreamError(provider, f"HTTP {status}", status) from None
    except httpx.TransportError as e:
        raise UpstreamError(provider, type(e).__name__) from None
    raise UpstreamError(provider, "no response")  # unreachable: tenacity either returns or raises


def json_or_error(provider: str, resp: httpx.Response) -> Any:
    """The JSON body of a 2xx response, else an `UpstreamError`. Read a provider's own error text first if needed."""
    if not resp.is_success:
        raise UpstreamError(provider, f"HTTP {resp.status_code}", resp.status_code)
    try:
        return resp.json()
    except ValueError:
        raise UpstreamError(provider, "returned a response that isn't JSON", resp.status_code) from None
