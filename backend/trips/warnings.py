"""Official weather warnings along each route, at the time the truck is there.

1. Every ~20 miles, NWS /points tells us which forecast zone, county and town a route is in.
2. Active alerts for those states are matched by zone code (or by polygon when the alert has one),
   and kept only if the truck reaches that stretch while the alert is in effect.
3. Jev triages each matched alert (does it matter to a heavy truck, what hazard, are roads closing).
4. The words shown are the NWS's own WHAT and IMPACTS lines, not generated text.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from shapely.geometry import Point, Polygon

from providers.jev import Triage, triage
from providers.nws import Alert, PointInfo, active_alerts
from trips import schemas as s

SAMPLE_EVERY_MI = 20.0
SEVERITY_RANK = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}
SUMMARY_MAX = 300


def sample_indices(n: int, interval_mi: float) -> list[int]:
    """Which checkpoints to look up: about one every SAMPLE_EVERY_MI, always including the last."""
    step = max(1, round(SAMPLE_EVERY_MI / interval_mi))
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return idx


def spread(infos: list[PointInfo | None], sampled: list[int], n: int) -> list[PointInfo | None]:
    """Give every checkpoint the answer of the nearest sampled checkpoint that has one."""
    known = [(i, info) for i, info in zip(sampled, infos, strict=True) if info is not None]
    if not known:
        return [None] * n
    return [min(known, key=lambda k: abs(k[0] - j))[1] for j in range(n)]


_SECTION = re.compile(r"\*\s*([A-Z ]+?)\.\.\.(.*?)(?=\n\s*\*\s*[A-Z ]+?\.\.\.|\Z)", re.S)


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if not text or text[-1] in ".!?" else text + "."


def _sentence_case(text: str) -> str:
    text = text.strip(" .").lower()
    return text[:1].upper() + text[1:] + "." if text else ""


def _trim(text: str, limit: int = SUMMARY_MAX) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "))
    return cut[: end + 1] if end > 60 else cut.rsplit(" ", 1)[0] + "…"


def plain_words(a: Alert) -> str:
    """The NWS's own plain sentences: WHAT, then IMPACTS; else the headline; else the opening lines."""
    sections = {k.strip(): _clean(v) for k, v in _SECTION.findall(a.description)}
    if "WHAT" in sections:
        return _trim(" ".join(x for x in (sections["WHAT"], sections.get("IMPACTS", "")) if x))
    if a.nws_headline:
        return _sentence_case(a.nws_headline)
    return _trim(_clean(a.description.replace("...", " ")))


@dataclass(frozen=True, slots=True)
class _Hit:
    route_id: str
    from_mi: float
    to_mi: float
    enter: int
    tz: str


def _hits(a: Alert, routes: list[s.RouteOut], zones: dict[str, list[PointInfo | None]]) -> list[_Hit]:
    out = []
    ends = a.ends if a.ends is not None else math.inf
    for r in routes:
        inside = []
        for cp, info in zip(r.checkpoints, zones[r.id], strict=True):
            if not a.starts <= cp.eta <= ends:
                continue
            if a.polygon is not None:
                hit = a.polygon.contains(Point(cp.lon, cp.lat))
            else:
                hit = info is not None and bool(info.zones & a.ugc)
            if hit:
                inside.append(cp)
        if inside:
            out.append(_Hit(r.id, inside[0].mile, inside[-1].mile, inside[0].eta, inside[0].tz))
    return out


def _warning(a: Alert, hits: list[_Hit], t: Triage, source: Literal["nws", "simulated"]) -> s.WarningOut:
    return s.WarningOut(
        id=a.id,
        event=a.event,
        severity=a.severity,
        area=a.area,
        starts=int(a.starts),
        ends=None if a.ends is None else int(a.ends),
        summary=plain_words(a),
        instruction=_trim(_clean(a.instruction), 240) if a.instruction else "",
        hazard=t.hazard,
        relevant=t.relevant,
        road_closure=t.road_closure,
        truck_risk=t.truck_risk,
        triage=t.by,
        source=source,
        url=a.url,
        routes=[
            s.WarningHitOut(route_id=h.route_id, from_mi=h.from_mi, to_mi=h.to_mi, enter=h.enter, tz=h.tz) for h in hits
        ],
    )


async def route_warnings(
    routes: list[s.RouteOut], zones: dict[str, list[PointInfo | None]], simulated: list[Alert] | None = None
) -> list[s.WarningOut]:
    """Warnings any route runs into, most important first. `simulated` replaces the live feed (demo)."""
    source: Literal["nws", "simulated"] = "nws" if simulated is None else "simulated"
    if simulated is None:
        states = {z[:2] for infos in zones.values() for info in infos if info for z in info.zones}
        alerts = await active_alerts(sorted(states))
    else:
        alerts = simulated
    matched = [(a, h) for a in alerts if (h := _hits(a, routes, zones))]
    verdicts = await triage([a for a, _ in matched])
    out = [_warning(a, h, verdicts[a.id], source) for a, h in matched]
    return sorted(out, key=lambda w: (not w.relevant, not w.road_closure, SEVERITY_RANK.get(w.severity, 4), w.starts))


# --- demo: warnings the NWS would plausibly issue for the simulated storm (providers/weather/demo.py)


def _ellipse(lat: float, lon: float, rlat: float, rlon: float) -> Polygon:
    return Polygon(
        [(lon + rlon * math.cos(t), lat + rlat * math.sin(t)) for t in (i * math.pi / 18 for i in range(36))]
    )


def demo_alerts(anchor_s: float) -> list[Alert]:
    h = 3600
    return [
        Alert(
            id=f"demo-winter-storm-{int(anchor_s)}",
            event="Winter Storm Warning",
            severity="Severe",
            headline="Winter Storm Warning (simulated)",
            nws_headline="",
            description=(
                "* WHAT...Heavy snow expected. Total snow accumulations of 6 to 10 inches, with up to\n"
                "14 inches over Raton Pass. Snowfall rates of 2 to 3 inches per hour at times.\n\n"
                "* WHERE...Raton Pass, Trinidad and the I-25 corridor.\n\n"
                "* WHEN...Through tonight.\n\n"
                "* IMPACTS...Travel could be very difficult to impossible. Roads, including\n"
                "Interstate 25 over Raton Pass, may close."
            ),
            instruction="If you must travel, keep an extra flashlight, food and water in your vehicle.",
            area="Raton Pass; Trinidad; Southern Colfax County",
            starts=anchor_s + 7 * h,
            ends=anchor_s + 22 * h,
            ugc=frozenset(),
            polygon=_ellipse(37.05, -104.5, 0.55, 0.5),
        ),
        Alert(
            id=f"demo-high-wind-{int(anchor_s)}",
            event="High Wind Warning",
            severity="Severe",
            headline="High Wind Warning (simulated)",
            nws_headline="",
            description=(
                "* WHAT...West winds 40 to 50 mph with gusts up to 65 mph.\n\n"
                "* WHERE...Northwest Kansas along Interstate 70.\n\n"
                "* WHEN...From this evening through Sunday morning.\n\n"
                "* IMPACTS...Travel will be difficult, especially for high profile vehicles. "
                "Blowing dust may reduce visibility."
            ),
            instruction="Drivers of high profile vehicles should consider delaying travel.",
            area="Sherman; Thomas; Logan; Gove; Trego",
            starts=anchor_s + 5 * h,
            ends=anchor_s + 23 * h,
            ugc=frozenset(),
            polygon=_ellipse(39.0, -101.0, 0.6, 1.8),
        ),
        Alert(
            id=f"demo-frost-{int(anchor_s)}",
            event="Frost Advisory",
            severity="Minor",
            headline="Frost Advisory (simulated)",
            nws_headline="",
            description=(
                "* WHAT...Temperatures as low as 33 will result in frost formation.\n\n"
                "* WHERE...The Texas Panhandle.\n\n"
                "* IMPACTS...Frost could harm sensitive outdoor vegetation."
            ),
            instruction="Take steps now to protect tender plants from the cold.",
            area="Potter; Randall; Oldham; Deaf Smith",
            starts=anchor_s,
            ends=anchor_s + 20 * h,
            ugc=frozenset(),
            polygon=_ellipse(35.2, -101.9, 0.7, 1.0),
        ),
    ]
