"""National Weather Service (api.weather.gov): where a point is, and which alerts are active.

Most NWS alerts name forecast zones and counties (UGC codes like COZ088 / COC071) and carry no
shape, so we don't intersect geometry: we ask /points which zones each sampled route point is
in, then match alerts by code. Alerts that do carry a polygon (storm-based warnings) are also
matched by shape, which is tighter than their county list.

/points answers never change for a place, so they are cached for a month per ~1 km cell; the
alert list is cached for a few minutes per set of states.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import h3
import shapely
import shapely.errors
from django.core.cache import cache
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from providers.http import UpstreamError, fetch, json_or_error

log = logging.getLogger(__name__)

PROVIDER = "National Weather Service"
BASE = "https://api.weather.gov"
HEADERS = {"Accept": "application/geo+json"}
POINT_RES = 7
POINT_TTL_S = 30 * 24 * 3600
MISS = "miss"
MISS_TTL_S = 10 * 60
ALERTS_TTL_S = 5 * 60
CONCURRENCY = 16


@dataclass(frozen=True, slots=True)
class PointInfo:
    zones: frozenset[str]  # forecast zone, county and fire zone UGC codes
    place: str  # nearest named place, "Trinidad, CO"
    state: str


@dataclass(frozen=True, slots=True)
class Alert:
    id: str
    event: str
    severity: str  # Extreme | Severe | Moderate | Minor | Unknown
    headline: str
    nws_headline: str
    description: str
    instruction: str
    area: str
    starts: float
    ends: float | None
    ugc: frozenset[str]
    polygon: BaseGeometry | None
    url: str | None = None


def _ugc(url: str | None) -> str | None:
    return url.rstrip("/").rsplit("/", 1)[-1] if url else None


async def _get(path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
    resp = await fetch(PROVIDER, "GET", f"{BASE}{path}", attempts=2, params=params, headers=HEADERS)
    data: dict[str, Any] = json_or_error(PROVIDER, resp)
    return data


async def _point(lat: float, lon: float, gate: asyncio.Semaphore) -> PointInfo | None:
    key = f"nws:pt:v1:{h3.latlng_to_cell(lat, lon, POINT_RES)}"
    if (hit := await cache.aget(key)) is not None:
        return hit if isinstance(hit, PointInfo) else None
    async with gate:
        try:
            p = (await _get(f"/points/{lat:.4f},{lon:.4f}"))["properties"]
        except (UpstreamError, KeyError, TypeError) as e:
            log.info("nws point %.3f,%.3f failed: %s", lat, lon, type(e).__name__)
            await cache.aset(key, MISS, timeout=MISS_TTL_S)  # don't make every trip wait on a bad point
            return None
    rel = p.get("relativeLocation", {}).get("properties", {})
    codes = {_ugc(p.get(k)) for k in ("forecastZone", "county", "fireWeatherZone")}
    info = PointInfo(
        zones=frozenset(c for c in codes if c),
        place=f"{rel.get('city', '')}, {rel.get('state', '')}".strip(", "),
        state=str(rel.get("state", "")),
    )
    await cache.aset(key, info, timeout=POINT_TTL_S)
    return info


_background: set[asyncio.Task[PointInfo | None]] = set()


async def points(coords: Sequence[tuple[float, float]], deadline_s: float) -> list[PointInfo | None]:
    """Zone codes and nearest place for each (lat, lon); None where NWS hasn't answered by the deadline.

    Points in the same ~1 km cell share one lookup. Lookups still running at the deadline carry on in the
    background and fill the cache, so the next trip through the same area is instant.
    """
    gate = asyncio.Semaphore(CONCURRENCY)
    cells = [h3.latlng_to_cell(lat, lon, POINT_RES) for lat, lon in coords]
    tasks: dict[str, asyncio.Task[PointInfo | None]] = {}
    for cell, (lat, lon) in zip(cells, coords, strict=True):
        if cell not in tasks:
            tasks[cell] = asyncio.create_task(_point(lat, lon, gate))
    await asyncio.wait(tasks.values(), timeout=deadline_s)
    for t in tasks.values():
        if not t.done():
            _background.add(t)
            t.add_done_callback(_background.discard)
    return [
        t.result() if t.done() and not t.cancelled() and t.exception() is None else None
        for t in (tasks[c] for c in cells)
    ]


def _ts(value: str | None) -> float | None:
    return datetime.fromisoformat(value).timestamp() if value else None


def parse_alert(feature: dict[str, Any]) -> Alert | None:
    p = feature.get("properties") or {}
    starts = _ts(p.get("onset")) or _ts(p.get("effective"))
    if not p.get("id") or starts is None:
        return None
    geom = feature.get("geometry")
    polygon = shapely.make_valid(shape(geom)) if geom else None
    params = p.get("parameters") or {}
    return Alert(
        id=str(p["id"]),
        event=str(p.get("event", "Weather alert")),
        severity=str(p.get("severity", "Unknown")),
        headline=str(p.get("headline") or ""),
        nws_headline=" ".join(params.get("NWSheadline") or []),
        description=str(p.get("description") or ""),
        instruction=str(p.get("instruction") or ""),
        area=str(p.get("areaDesc") or ""),
        starts=starts,
        ends=_ts(p.get("ends")) or _ts(p.get("expires")),
        ugc=frozenset((p.get("geocode") or {}).get("UGC") or []),
        polygon=polygon,
        url=p.get("@id"),
    )


async def active_alerts(states: Sequence[str]) -> list[Alert]:
    """Active, actual alerts for these states (two-letter codes)."""
    area = ",".join(sorted(set(states)))
    if not area:
        return []
    key = f"nws:alerts:v1:{area}"
    if (hit := await cache.aget(key)) is not None:
        return list(hit)
    data = await _get("/alerts/active", {"area": area, "status": "actual"})
    alerts = []
    for feature in data.get("features", []):
        try:
            if (alert := parse_alert(feature)) is not None:
                alerts.append(alert)
        except (KeyError, TypeError, ValueError, shapely.errors.ShapelyError) as e:  # one malformed alert
            log.warning("skipping an NWS alert that didn't parse: %s", type(e).__name__)
    await cache.aset(key, alerts, timeout=ALERTS_TTL_S)
    return alerts
