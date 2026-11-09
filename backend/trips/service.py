"""Plan a trip end to end: routes → clocks → checkpoints → corridor → weather → risk → ranking → warnings.

Network calls (routing, weather, NWS) are async; the number crunching is pure engine code run in a
worker thread so the event loop stays free.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

import h3
import numpy as np
from django.core.cache import cache

from engine.advisor import DepartureAdvice, sweep_departures
from engine.corridor import Corridor, build_corridor
from engine.eta import DEFAULT_HOS, DriveProfile, TripClock
from engine.evaluate import RouteEvaluation, RoutePlan, evaluate
from engine.geometry import Polyline
from engine.sampling import Checkpoints, place_checkpoints
from engine.scoring import Ranking, rank
from engine.units import HOUR
from engine.weather import WeatherGrid
from providers import nws, osm_places
from providers.nws import Alert, PointInfo
from providers.osm_places import OnRoute
from providers.routing import LatLon, RouteCandidate, get_routing_provider
from providers.routing.alternatives import distinct_routes
from providers.weather import WeatherProvider, get_weather_provider
from providers.weather.demo import DemoStormWeather, demo_alerts
from trips import schemas as s
from trips.limits import (
    ADVISOR_HOURS,
    CHECKPOINT_RES,
    CORRIDOR_HALF_WIDTH_MI,
    HEATMAP_ANCHOR_LEAD_H,
    MAX_LEAD_DAYS,
    POINTS_WAIT_S,
    ROUTE_CACHE_S,
    STOP_MAX_OFF_MI,
    TRIP_CACHE_S,
    TRUCK_MAX_MPH,
    WARNINGS_WAIT_S,
    WEIGH_MAX_OFF_MI,
)
from trips.serialize import departure_advice_out, heatmap_out, recommendation_out, routes_out
from trips.timezones import tz_at
from trips.warnings import route_warnings, sample_indices, spread

log = logging.getLogger(__name__)

ROUTE_LABELS = "ABCDE"
COARSEST_SAMPLE_RES = 3  # corridor sampling gets coarser down to this before the trip is refused


class TripError(ValueError):
    """A problem with the request the user can fix (time, place, spacing); shown to them as is."""


async def _routes(origin: LatLon, dest: LatLon, depart: datetime, load_lb: float) -> list[RouteCandidate]:
    provider = get_routing_provider()
    raw = f"{provider.name}|{origin}|{dest}|{depart.astimezone(UTC):%Y%m%d%H}|{round(load_lb, -3)}"
    key = "routes:v1:" + hashlib.sha1(raw.encode()).hexdigest()
    if (hit := await cache.aget(key)) is not None:
        return list(hit)
    routes = await distinct_routes(provider, origin, dest, depart, load_lb)
    if routes:
        await cache.aset(key, routes, timeout=ROUTE_CACHE_S)
    return routes


def _stop_places(line: Polyline) -> list[OnRoute]:
    """Truck stops and rest areas by the route, where breaks and rests can be planned."""
    found = osm_places.along(line, "truck_stop", STOP_MAX_OFF_MI) + osm_places.along(line, "rest_area", STOP_MAX_OFF_MI)
    return sorted(found, key=lambda p: p.mile)


def _weigh_stations(line: Polyline) -> list[OnRoute]:
    """One per mile: a station is often mapped once per direction of travel."""
    out: list[OnRoute] = []
    for w in osm_places.along(line, "weigh", WEIGH_MAX_OFF_MI):
        if not out or w.mile - out[-1].mile > 1.0:
            out.append(w)
    return out


@dataclass
class _Prepared:
    staged: list[tuple[Polyline, TripClock, Checkpoints]]
    corridor: Corridor
    checkpoint_cells: list[list[str]]
    checkpoint_latlon: list[list[tuple[float, float]]]
    weather_cells: list[str]
    stop_places: list[list[OnRoute]]
    weigh_stations: list[list[OnRoute]]


def _prepare(cands: list[RouteCandidate], depart_s: float, req: s.TripRequest, weather: WeatherProvider) -> _Prepared:
    lines: list[Polyline] = []
    staged: list[tuple[Polyline, TripClock, Checkpoints]] = []
    cp_cells: list[list[str]] = []
    cp_latlon: list[list[tuple[float, float]]] = []
    stop_places: list[list[OnRoute]] = []
    for c in cands:
        line = Polyline.from_coords(c.coords)
        profile = DriveProfile(line.cum_mi, c.cum_drive_s)
        if not c.truck_aware:
            profile = profile.capped(TRUCK_MAX_MPH)
        places = _stop_places(line)
        stop_places.append(places)
        places_mi = np.array([p.mile for p in places])
        clock = TripClock.build(depart_s, profile, hos=DEFAULT_HOS if req.hos else None, places_mi=places_mi)
        cps = place_checkpoints(line.length_mi, req.interval_mi)
        lats, lons = line.points_at(cps.miles)
        points = [(float(a), float(b)) for a, b in zip(lats, lons, strict=True)]
        cp_latlon.append(points)
        cp_cells.append([h3.latlng_to_cell(lat, lon, CHECKPOINT_RES) for lat, lon in points])
        lines.append(line)
        staged.append((line, clock, cps))

    budget = weather.point_budget
    checkpoint_set = {c for cells in cp_cells for c in cells}
    if len(checkpoint_set) > budget:
        raise TripError("This trip is too long for checkpoints that close together. Try every 25 or 50 miles.")
    # Coarsen the corridor's weather sampling until the trip fits the budget; the heatmap's own
    # cells stay the same size (sampled values are interpolated onto them).
    res = weather.sample_res
    corridor = build_corridor(lines, CORRIDOR_HALF_WIDTH_MI, sample_res=res)
    while len(checkpoint_set) + len(corridor.sample_cells) > budget and res > COARSEST_SAMPLE_RES:
        res -= 1
        corridor = build_corridor(lines, CORRIDOR_HALF_WIDTH_MI, sample_res=res)
    weather_cells = sorted(checkpoint_set | set(corridor.sample_cells))
    if len(weather_cells) > budget:
        raise TripError("This trip is too long to check the weather along all three routes. Try a shorter trip.")
    weigh = [_weigh_stations(line) for line in lines]
    return _Prepared(staged, corridor, cp_cells, cp_latlon, weather_cells, stop_places, weigh)


@dataclass
class _Computed:
    evals: list[RouteEvaluation]
    ranking: Ranking
    advice: DepartureAdvice
    row_of: dict[str, int]


def _compute(req: s.TripRequest, prep: _Prepared, grid: WeatherGrid) -> _Computed:
    row_of = {c: i for i, c in enumerate(prep.weather_cells)}
    plans = [
        RoutePlan(ROUTE_LABELS[k], line, clock, cps, np.array([row_of[c] for c in cells], dtype=np.intp))
        for k, ((line, clock, cps), cells) in enumerate(zip(prep.staged, prep.checkpoint_cells, strict=True))
    ]
    evals = [evaluate(p, grid, req.load_lb, req.wind_basis) for p in plans]
    ranking = rank([e.score for e in evals])
    advice = sweep_departures(plans, grid, req.load_lb, ADVISOR_HOURS, req.wind_basis)
    return _Computed(evals, ranking, advice, row_of)


async def _warnings(
    routes: list[s.RouteOut],
    lookup: asyncio.Task[list[PointInfo | None]],
    sampled: list[list[int]],
    simulated: list[Alert] | None,
) -> tuple[list[s.WarningOut], Literal["ok", "unavailable"]]:
    """Name the places along each route and find official warnings.

    Warnings are an extra: whatever goes wrong here is logged and reported as "unavailable",
    never allowed to fail a trip whose routes and forecast are already computed.
    """
    try:
        infos: list[PointInfo | None] | None = await lookup
    except Exception:
        log.exception("NWS place lookup failed")
        infos = None
    if infos is not None and not any(infos):
        infos = None
    zones: dict[str, list[PointInfo | None]] = {}
    offset = 0
    for r, idx in zip(routes, sampled, strict=True):
        part: list[PointInfo | None] = infos[offset : offset + len(idx)] if infos else [None] * len(idx)
        offset += len(idx)
        zones[r.id] = spread(part, idx, len(r.checkpoints))
        for cp, info in zip(r.checkpoints, zones[r.id], strict=True):
            cp.place = info.place if info else None
    if infos is None and simulated is None:
        return [], "unavailable"
    try:
        return await asyncio.wait_for(route_warnings(routes, zones, simulated), WARNINGS_WAIT_S), "ok"
    except Exception:
        log.exception("weather warnings unavailable")
        return [], "unavailable"


async def plan_trip(req: s.TripRequest) -> s.TripOut:
    t0 = time.perf_counter()
    origin_tz = tz_at(req.origin.lat, req.origin.lon)
    # A clock time skipped or repeated by a daylight-saving change resolves as zoneinfo does (fold=0):
    # a skipped 2:30 AM is read as 3:30 AM, a repeated 1:30 AM as the first one.
    depart_s = req.departure_local.replace(tzinfo=ZoneInfo(origin_tz)).timestamp()
    now = time.time()
    if depart_s < now - HOUR:
        raise TripError("Departure is in the past.")
    if depart_s > now + MAX_LEAD_DAYS * 24 * HOUR:
        raise TripError(f"Departure must be within {MAX_LEAD_DAYS} days: forecasts beyond that aren't decision-grade.")

    o, d = LatLon(req.origin.lat, req.origin.lon), LatLon(req.destination.lat, req.destination.lon)
    cands = await _routes(o, d, datetime.fromtimestamp(depart_s, UTC), req.load_lb)
    if not cands:
        raise TripError("No truck route found between these places.")
    t_route = time.perf_counter()

    demo = DemoStormWeather() if req.weather == "demo_storm" else None
    weather: WeatherProvider = demo or get_weather_provider()
    prep = await asyncio.to_thread(_prepare, cands, depart_s, req, weather)
    # NWS zone and town lookups run while the forecast downloads.
    sampled = [sample_indices(len(ll), req.interval_mi) for ll in prep.checkpoint_latlon]
    coords = [ll[i] for ll, idx in zip(prep.checkpoint_latlon, sampled, strict=True) for i in idx]
    lookup = asyncio.create_task(nws.points(coords, POINTS_WAIT_S))
    try:
        grid = await weather.grid(prep.weather_cells)
        t_wx = time.perf_counter()

        done = await asyncio.to_thread(_compute, req, prep, grid)
        routes = routes_out(done.evals, cands, done.ranking, depart_s, prep.stop_places, prep.weigh_stations)
        warnings, warnings_status = await _warnings(
            routes, lookup, sampled, demo_alerts(demo.anchor_s) if demo else None
        )
    finally:
        lookup.cancel()  # no-op once finished; stops the lookups if planning failed part-way
    # The slider starts now, unless the trip leaves so much later that it would never reach it.
    heat_start = depart_s if depart_s - now > HEATMAP_ANCHOR_LEAD_H * HOUR else now
    heatmap = heatmap_out(prep.corridor, grid, done.row_of, req.load_lb, req.wind_basis, heat_start)
    t_end = time.perf_counter()

    trip = s.TripOut(
        id=uuid.uuid4().hex[:12],
        created=int(now),
        origin=s.PlaceOut(**req.origin.model_dump()),
        destination=s.PlaceOut(**req.destination.model_dump()),
        departure=int(depart_s),
        origin_tz=origin_tz,
        load_lb=req.load_lb,
        interval_mi=req.interval_mi,
        wind_basis=req.wind_basis,
        hos=req.hos,
        forecast_issued=int(grid.issued_s),
        weather_model=weather.model,
        weather_points=len(prep.weather_cells),
        routes=routes,
        recommendation=recommendation_out(done.ranking, done.advice.best_offset_h),
        departure_advice=departure_advice_out(done.advice, depart_s),
        heatmap=heatmap,
        warnings=warnings,
        warnings_status=warnings_status,
        timings=s.TimingsOut(
            routing_ms=round((t_route - t0) * 1000),
            weather_ms=round((t_wx - t_route) * 1000),
            compute_ms=round((t_end - t_wx) * 1000),
            total_ms=round((t_end - t0) * 1000),
        ),
    )
    await cache.aset(f"trip:{trip.id}", trip.model_dump_json(), timeout=TRIP_CACHE_S)
    return trip


async def get_trip(trip_id: str) -> s.TripOut | None:
    raw = await cache.aget(f"trip:{trip_id}")
    return s.TripOut.model_validate_json(raw) if raw else None
