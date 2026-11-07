"""Jev, TypeSafe AI's decision model: typed answers (yes/no probabilities, picks from a list) about text.

Jev judges rather than writes, and can't do arithmetic, so callers ask narrow questions and combine
the answers in code. Every caller has a keyword fallback for when Jev isn't configured or is slow.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Question, RetryPolicy, SystemOneResponse, TypeSafeError

from config.env import get_env

log = logging.getLogger(__name__)

WAIT_S = 4.0  # per request, retries included; past this the caller's fallback is better than waiting


@lru_cache(maxsize=1)
def client() -> AsyncTypeSafeClient | None:
    env = get_env()
    if env.typesafe_api_key is None:
        return None
    return AsyncTypeSafeClient(
        api_key=env.typesafe_api_key.get_secret_value(),
        model=env.typesafe_model,
        timeout=WAIT_S,
        retry=RetryPolicy(max_retries=1),
    )


async def ask(state: str | dict[str, Any], questions: Mapping[str, Question]) -> SystemOneResponse | None:
    """Jev's answers, or None if Jev is unavailable, fails or takes longer than WAIT_S."""
    jev = client()
    if jev is None:
        return None
    try:
        return await asyncio.wait_for(jev.system_one(state=state, questions=questions), WAIT_S)
    except (TypeSafeError, TimeoutError) as e:
        log.warning("jev unavailable: %s", type(e).__name__)
        return None
