"""Jev (TypeSafe) reads a weather alert and answers three typed questions a dispatcher would ask.

Jev returns decisions, not prose: a probability that the alert matters to a heavy, high-sided
truck, which kind of hazard it is, and whether it warns of closed roads or impossible travel.
Each question is one narrow judgement; code combines them. If Jev is unavailable the same
answers come from a keyword table, and the result says which one was used.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from django.core.cache import cache
from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, Question, RetryPolicy, TypeSafeError

from config.env import get_env
from providers.nws import Alert

log = logging.getLogger(__name__)

Hazard = Literal["snow_ice", "wind", "flood", "visibility", "storm", "temperature", "other"]
TRIAGE_TTL_S = 6 * 3600
TIMEOUT_S = 6.0

HAZARDS: dict[Hazard, str] = {
    "snow_ice": "Snow, ice, sleet or freezing rain on the roads",
    "wind": "Strong or gusty wind",
    "flood": "Flooding or very heavy rain",
    "visibility": "Fog, smoke or blowing dust that cuts visibility",
    "storm": "Thunderstorms, hail or tornadoes",
    "temperature": "Extreme heat or cold",
    "other": "Something else, or not weather on the road",
}

QUESTIONS: dict[str, Question] = {
    "truck": Noul(
        instructions=(
            "Would the conditions in this weather alert make it more dangerous to drive a loaded, "
            "high-sided tractor-trailer through the area while the alert is in effect?"
        )
    ),
    "hazard": Choice(
        instructions="What is the main hazard to drivers in this alert?",
        criteria={str(k): v for k, v in HAZARDS.items()},
    ),
    "closure": Noul(
        instructions=(
            "Does the alert say that roads may close, or that travel could become very difficult or impossible?"
        )
    ),
}


@dataclass(frozen=True, slots=True)
class Triage:
    relevant: bool
    truck_risk: float  # 0..1
    hazard: Hazard
    road_closure: bool
    by: Literal["jev", "rules"]


@lru_cache(maxsize=1)
def _client() -> AsyncTypeSafeClient | None:
    env = get_env()
    if env.typesafe_api_key is None:
        return None
    return AsyncTypeSafeClient(
        api_key=env.typesafe_api_key.get_secret_value(),
        model=env.typesafe_model,
        timeout=TIMEOUT_S,
        retry=RetryPolicy(max_retries=1),
    )


def _state(a: Alert) -> dict[str, str]:
    return {
        "event": a.event,
        "severity": a.severity,
        "headline": a.nws_headline or a.headline,
        "description": a.description[:3000],
        "instructions": a.instruction[:1000],
    }


async def _ask_jev(jev: AsyncTypeSafeClient, a: Alert) -> Triage:
    res = await jev.system_one(state=_state(a), questions=QUESTIONS)
    risk = res.nouls["truck"].noul
    choice = res.choices["hazard"].choice
    hazard: Hazard = next((h for h in HAZARDS if h == choice), "other")
    return Triage(
        relevant=risk >= 0.5,
        truck_risk=round(risk, 3),
        hazard=hazard,
        road_closure=res.nouls["closure"].noul >= 0.5,
        by="jev",
    )


# Fallback: NWS event names are a fixed vocabulary, so a keyword table is a fair second best.
_RULES: tuple[tuple[str, Hazard], ...] = (
    ("blizzard", "snow_ice"),
    ("winter", "snow_ice"),
    ("ice", "snow_ice"),
    ("snow", "snow_ice"),
    ("freezing rain", "snow_ice"),
    ("sleet", "snow_ice"),
    ("high wind", "wind"),
    ("wind", "wind"),
    ("flood", "flood"),
    ("fog", "visibility"),
    ("dust", "visibility"),
    ("smoke", "visibility"),
    ("tornado", "storm"),
    ("thunderstorm", "storm"),
    ("heat", "temperature"),
    ("cold", "temperature"),
)
_NOT_ON_ROAD = ("frost", "freeze", "rip current", "beach", "marine", "small craft", "gale", "air quality", "red flag")


def rules_triage(a: Alert) -> Triage:
    name = a.event.lower()
    hazard: Hazard = next((h for k, h in _RULES if k in name), "other")
    relevant = hazard != "other" and not any(k in name for k in _NOT_ON_ROAD)
    text = f"{a.description} {a.instruction}".lower()
    closure = any(k in text for k in ("road closure", "roads closed", "travel could be very difficult", "impossible"))
    return Triage(relevant, 0.8 if relevant else 0.1, hazard, closure, "rules")


async def triage(alerts: list[Alert]) -> dict[str, Triage]:
    """Triage each alert once; answers are cached by alert id (an alert's text never changes)."""
    jev = _client()

    async def one(a: Alert) -> tuple[str, Triage]:
        key = f"jev:alert:v1:{a.id}"
        if (hit := await cache.aget(key)) is not None:
            return a.id, hit
        if jev is None:
            return a.id, rules_triage(a)
        try:
            t = await _ask_jev(jev, a)
        except (TypeSafeError, KeyError, AttributeError, TimeoutError) as e:
            log.warning("jev triage failed for %s: %s", a.event, type(e).__name__)
            return a.id, rules_triage(a)
        await cache.aset(key, t, timeout=TRIAGE_TTL_S)
        return a.id, t

    return dict(await asyncio.gather(*(one(a) for a in alerts)))


# --- Reading a typed trip: which day and hour the driver means ("tomorrow after lunch").
# Jev can't do date arithmetic, so code offers concrete labelled days; Jev only matches words to them.
# "unstated" goes first: if Jev leans on the first option, it leans towards not guessing.


@dataclass(frozen=True, slots=True)
class Departure:
    day: str  # a key of the offered days, or "unstated"
    day_confidence: float
    hour: str  # "h00".."h23", "now" or "unstated"
    hour_confidence: float


HOURS: dict[str, str] = {"unstated": "No time of day is mentioned", "now": "Right now, as soon as possible"} | {
    f"h{h:02d}": f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}"
    + (" (midnight)" if h == 0 else " (noon)" if h == 12 else "")
    for h in range(24)
}


async def read_departure(text: str, days: dict[str, str]) -> Departure | None:
    """Day and hour the text asks to leave, as keys of `days` / HOURS; None if Jev is unavailable."""
    jev = _client()
    if jev is None:
        return None
    questions: dict[str, Question] = {
        "day": Choice(
            instructions="On which day does the driver want to leave?",
            criteria={"unstated": "No day is mentioned"} | days,
        ),
        "hour": Choice(instructions="At about what time of day does the driver want to leave?", criteria=HOURS),
    }
    try:
        res = await jev.system_one(state=text, questions=questions)
    except (TypeSafeError, TimeoutError) as e:
        log.warning("jev could not read the departure: %s", type(e).__name__)
        return None
    day, hour = res.choices["day"], res.choices["hour"]
    return Departure(day.choice, day.confidence, hour.choice, hour.confidence)
