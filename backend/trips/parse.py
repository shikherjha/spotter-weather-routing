"""Fill the trip form from one sentence: "Dallas to Denver tomorrow after lunch, 42k lbs".

Exact things are read by code: the two places (then geocoded), the load ("42k lbs", "21 tons"),
an explicit clock time ("6:30 pm") and the checkpoint spacing. Fuzzy timing ("after lunch",
"first thing Monday", "tonight") is a judgement, so Jev picks the day and hour from concrete
options. Every field the parser filled is returned, plus which ones deserve a second look.
The form is filled for the driver to check; nothing is planned until they press the button.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from typesafe_sdk import Choice, Question

from providers import jev
from providers.places import Place, search_places
from trips import schemas as s
from trips.limits import MAX_LEAD_DAYS
from trips.timezones import tz_at

SURE = 0.6  # below this Jev confidence the field is flagged for checking
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

_STOP = (
    r"(?=$|[,.;!?]|\s+(?:today|tomorrow|tonight|this|next|on|at|by|around|about|after|before|leaving|leave|"
    r"departing|depart|with|carrying|hauling|loaded|every|asap|now|in|first|early|late|sometime|midday|noon|"
    + "|".join(WEEKDAYS)
    + r")\b|\s+\d)"
)
_PLACE = r"(?P<{}>[A-Za-z][\w .'-]*?(?:,\s*[A-Za-z]{{2,}})?)"
_PATTERNS = (
    re.compile(r"\bfrom\s+" + _PLACE.format("a") + r"\s+(?:to|→|->)\s+" + _PLACE.format("b") + _STOP, re.I),
    re.compile(r"\bto\s+" + _PLACE.format("b") + r"\s+from\s+" + _PLACE.format("a") + _STOP, re.I),
    re.compile(r"^\s*" + _PLACE.format("a") + r"\s+(?:to|→|->|-)\s+" + _PLACE.format("b") + _STOP, re.I),
)
_LOAD = re.compile(r"(\d+(?:[.,]\d+)*)\s*(k\b|thousand\b)?\s*(lbs?\b|pounds?\b|#|tons?\b)?", re.I)
_CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\.?\b|\b(noon|midnight)\b", re.I)
_EVERY = re.compile(r"every\s+(10|25|50)\s*(?:mi|miles?)\b", re.I)
SPACINGS: dict[str, Literal[10, 25, 50]] = {"10": 10, "25": 25, "50": 50}


@dataclass(frozen=True, slots=True)
class Departure:
    day: str  # a key of day_options(), or "unstated"
    day_confidence: float
    hour: str  # "h00".."h23", "now" or "unstated"
    hour_confidence: float


# Jev can't do date arithmetic, so it picks from concrete, labelled options. "unstated" goes first:
# if Jev leans towards the first option, it leans towards not guessing.
HOURS: dict[str, str] = {"unstated": "No time of day is mentioned", "now": "Right now, as soon as possible"} | {
    f"h{h:02d}": f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}"
    + (" (midnight)" if h == 0 else " (noon)" if h == 12 else "")
    for h in range(24)
}


async def read_departure(text: str, days: dict[str, str]) -> Departure | None:
    """Jev's reading of when the driver wants to leave; None if Jev is unavailable."""
    questions: dict[str, Question] = {
        "day": Choice(
            instructions="On which day does the driver want to leave?",
            criteria={"unstated": "No day is mentioned"} | days,
        ),
        "hour": Choice(instructions="At about what time of day does the driver want to leave?", criteria=HOURS),
    }
    res = await jev.ask(text, questions)
    if res is None:
        return None
    day, hour = res.choices["day"], res.choices["hour"]
    return Departure(day.choice, day.confidence, hour.choice, hour.confidence)


@dataclass
class Parsed:
    origin: str | None = None
    destination: str | None = None
    load_lb: float | None = None
    interval_mi: Literal[10, 25, 50] | None = None
    clock: tuple[int, int] | None = None  # (hour, minute) when written exactly
    unsure: list[Literal["origin", "destination", "departure"]] = field(default_factory=list)


def _place(raw: str) -> str:
    """Keep the place itself: "get to Denver" -> "Denver"."""
    return re.split(r"\s(?:to|from)\s", f" {raw.strip()} ", flags=re.I)[-1].strip()


def read_text(text: str) -> Parsed:
    """Everything code can read exactly, without any network calls."""
    p = Parsed()
    for pat in _PATTERNS:
        if m := pat.search(text):
            p.origin, p.destination = _place(m["a"]), _place(m["b"])
            break
    for m in _LOAD.finditer(text):
        number, thousand, unit = m.groups()
        if not (thousand or unit):
            continue  # a bare number is more likely a time or a highway
        value = float(number.replace(",", ""))
        if thousand:
            value *= 1000
        if unit and unit.lower().startswith("ton"):
            value *= 2000
        if 1 <= value <= 120_000:
            p.load_lb = value
            break
    if m := _EVERY.search(text):
        p.interval_mi = SPACINGS[m[1]]
    if m := _CLOCK.search(text):
        if m[4]:
            p.clock = (12, 0) if m[4].lower() == "noon" else (0, 0)
        else:
            h = int(m[1]) % 12 + (12 if m[3].lower() == "p" else 0)
            p.clock = (h, int(m[2] or 0))
    return p


def day_options(now: datetime) -> dict[str, str]:
    """Concrete, labelled days for Jev to choose from: "d0" = today ... "d5"."""
    out = {}
    for i in range(MAX_LEAD_DAYS + 1):
        d = now + timedelta(days=i)
        date = f"{d.strftime('%A, %B')} {d.day}"
        out[f"d{i}"] = f"Today, {date}" if i == 0 else f"Tomorrow, {date}" if i == 1 else date
    return out


def rules_departure(text: str, now: datetime) -> Departure:
    """Keyword fallback when Jev is unavailable."""
    t = text.lower()
    day = "unstated"
    if "tomorrow" in t:
        day = "d1"
    elif re.search(r"\b(today|tonight|this (morning|afternoon|evening))\b", t):
        day = "d0"
    else:
        for i in range(MAX_LEAD_DAYS + 1):
            if re.search(rf"\b{(now + timedelta(days=i)).strftime('%A').lower()}\b", t):
                day = f"d{i}"
                break
    hour = "unstated"
    if re.search(r"\b(now|asap|right away)\b", t):
        hour = "now"
    else:
        for words, h in ((r"tonight|evening", 19), (r"afternoon|after lunch", 13), (r"morning|first thing", 7)):
            if re.search(rf"\b({words})\b", t):
                hour = f"h{h:02d}"
                break
    return Departure(day, 1.0, hour, 1.0)


def combine(by_jev: Departure | None, rules: Departure) -> Departure:
    """Jev's reading, with the keyword rules filling anything Jev left unstated (flagged for checking)."""
    if by_jev is None:
        return rules
    day, day_c = (
        (by_jev.day, by_jev.day_confidence)
        if by_jev.day != "unstated"
        else (rules.day, 0.0 if rules.day != "unstated" else 1.0)
    )
    hour, hour_c = (
        (by_jev.hour, by_jev.hour_confidence)
        if by_jev.hour != "unstated"
        else (rules.hour, 0.0 if rules.hour != "unstated" else 1.0)
    )
    return Departure(day, day_c, hour, hour_c)


def resolve_departure(d: Departure, clock: tuple[int, int] | None, now: datetime) -> tuple[datetime | None, bool]:
    """Turn day + hour choices into a wall-clock time at the origin. Returns (time, unsure)."""
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    if d.hour == "now":
        return next_hour, False
    if clock is not None:
        hm, unsure = clock, d.day_confidence < SURE and d.day != "unstated"
    elif d.hour.startswith("h"):
        hm, unsure = (int(d.hour[1:]), 0), d.hour_confidence < SURE or d.day_confidence < SURE
    elif d.day != "unstated":
        return None, True  # a day but no time: let the driver pick the hour
    else:
        return None, False
    days = int(d.day[1:]) if d.day.startswith("d") else 0
    when = (now + timedelta(days=days)).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
    if d.day == "unstated" and when < now:
        when += timedelta(days=1)  # "at 6 am" said in the afternoon means tomorrow
    return when, unsure or when < now


async def parse_trip(text: str, browser_tz: str) -> s.ParsedTripOut:
    p = read_text(text)
    places = {}
    roles: tuple[tuple[Literal["origin", "destination"], str | None], ...] = (
        ("origin", p.origin),
        ("destination", p.destination),
    )
    for role, query in roles:
        if query:
            found = await search_places(query, limit=1)
            if found:
                places[role] = found[0]
            else:
                p.unsure.append(role)
    origin = places.get("origin")
    tz = ZoneInfo(tz_at(origin.lat, origin.lon) if origin else browser_tz)
    now = datetime.now(tz)
    by_jev = await read_departure(text, day_options(now))
    departure, unsure = resolve_departure(combine(by_jev, rules_departure(text, now)), p.clock, now)
    if unsure:
        p.unsure.append("departure")
    return s.ParsedTripOut(
        origin=_out(places.get("origin")),
        destination=_out(places.get("destination")),
        departure_local=departure.strftime("%Y-%m-%dT%H:%M") if departure else None,
        load_lb=p.load_lb,
        interval_mi=p.interval_mi,
        unsure=p.unsure,
        read_by="jev" if by_jev else "rules",
    )


def _out(place: Place | None) -> s.PlaceOut | None:
    return s.PlaceOut(label=place.label, lat=place.lat, lon=place.lon) if place else None
