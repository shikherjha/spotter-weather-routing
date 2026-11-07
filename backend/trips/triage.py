"""Does an official weather alert matter to a loaded, high-sided truck?

Jev answers three narrow questions per alert: would it make driving such a truck more dangerous,
what is the main hazard, and does it warn of closed roads. If Jev can't answer, a keyword table
over the NWS's fixed event names gives the same three answers, and the result says which was used.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from django.core.cache import cache
from typesafe_sdk import Choice, Noul, Question

from providers import jev
from providers.nws import Alert
from trips.schemas import Hazard

TRIAGE_TTL_S = 6 * 3600  # an alert's text never changes; its id changes when the NWS updates it
LIKELY = 0.5

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


def _state(a: Alert) -> dict[str, str]:
    return {
        "event": a.event,
        "severity": a.severity,
        "headline": a.nws_headline or a.headline,
        "description": a.description[:3000],
        "instructions": a.instruction[:1000],
    }


# Most specific first: "wind chill" is about cold, not wind.
_KEYWORDS: tuple[tuple[str, Hazard], ...] = (
    ("wind chill", "temperature"),
    ("blizzard", "snow_ice"),
    ("winter", "snow_ice"),
    ("ice", "snow_ice"),
    ("snow", "snow_ice"),
    ("freezing rain", "snow_ice"),
    ("sleet", "snow_ice"),
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
_NOT_ON_THE_ROAD = (
    "frost",
    "freeze",
    "rip current",
    "beach",
    "marine",
    "small craft",
    "gale",
    "air quality",
    "red flag",
)
_CLOSURE_WORDS = ("road closure", "roads closed", "roads may close", "travel could be very difficult", "impossible")


def rules_triage(a: Alert) -> Triage:
    name = a.event.lower()
    hazard: Hazard = next((h for k, h in _KEYWORDS if k in name), "other")
    relevant = hazard != "other" and not any(k in name for k in _NOT_ON_THE_ROAD)
    text = f"{a.description} {a.instruction}".lower()
    closure = any(k in text for k in _CLOSURE_WORDS)
    return Triage(relevant, 1.0 if relevant else 0.0, hazard, closure, "rules")


async def _triage_one(a: Alert) -> Triage:
    key = f"triage:v1:{a.id}"
    if isinstance(hit := await cache.aget(key), Triage):
        return hit
    res = await jev.ask(_state(a), QUESTIONS)
    if res is None:
        return rules_triage(a)
    risk = res.nouls["truck"].noul
    hazard: Hazard = next((h for h in HAZARDS if h == res.choices["hazard"].choice), "other")
    t = Triage(risk >= LIKELY, round(risk, 3), hazard, res.nouls["closure"].noul >= LIKELY, "jev")
    await cache.aset(key, t, timeout=TRIAGE_TTL_S)
    return t


async def triage(alerts: list[Alert]) -> dict[str, Triage]:
    """Triage every alert concurrently; each falls back to the keyword rules on its own."""
    results = await asyncio.gather(*(_triage_one(a) for a in alerts))
    return {a.id: t for a, t in zip(alerts, results, strict=True)}
