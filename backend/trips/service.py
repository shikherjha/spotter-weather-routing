"""Plan a trip end to end: routes -> clocks -> checkpoints -> corridor -> weather -> risk -> ranking.

I/O (routing, weather) is async and concurrent-friendly; the CPU part is pure engine
code run in a worker thread so the event loop stays free.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo

import h3
import httpx
import numpy as np
import shapely
from django.core.cache import cache
from shapely.geometry import LineString
from timezonefinder import TimezoneFinder

from engine.advisor import sweep_departures
from engine.corridor import SAMPLE_RES, Corridor, build_corridor
from engine.eta import DEFAULT_HOS, HOUR, DriveProfile, TripClock
from engine.evaluate import RouteEvaluation, RoutePlan, evaluate
from engine.geometry import Polyline
from engine.rules import levels_array
from engine.sampling import Checkpoints, place_checkpoints
from engine.scoring import CRITERIA, Advice, Ranking, rank
from engine.weather import WeatherGrid
from providers import nws
from providers.http import UpstreamError
from providers.nws import Alert, PointInfo
from providers.routing import LatLon, RouteCandidate, get_routing_provider
from providers.routing.alternatives import distinct_routes
from providers.weather.demo import DemoStormWeather
from providers.weather.openmeteo import get_weather_provider
from trips import schemas as s
from trips.warnings import demo_alerts, route_warnings, sample_indices, spread

log = logging.getLogger(__name__)

TRUCK_MAX_MPH = 65.0  # cap for car-speed providers (typical governed truck speed)
CORRIDOR_HALF_WIDTH_MI = 15.0
CHECKPOINT_RES = 7  # ~1.2 km: weather is fetched at the cell centre, shared across routes
HEATMAP_HOURS = 49  # 0..48 h
WEATHER_POINT_BUDGET = 900  # stay under one Open-Meteo batch and the free per-minute quota
ADVISOR_HOURS = range(0, 25)
ROUTE_CACHE_S = 30 * 60
TRIP_CACHE_S = 24 * 3600
MAX_LEAD_DAYS = 5
ROUTE_LABELS = "ABCDE"
POINTS_WAIT_S = 5.0  # counted from when the lookup starts, alongside the forecast download
WARNINGS_WAIT_S = 8.0


class TripError(ValueError):
    """A user-facing problem with the request (bad time, no route, ...)."""


@lru_cache(maxsize=1)
def _tzf() -> TimezoneFinder:
    return TimezoneFinder(in_memory=True)


def tz_at(lat: float, lon: float) -> str:
    return _tzf().timezone_at(lng=lon, lat=lat) or "UTC"


def _b64(arr: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(arr, dtype=np.uint8).tobytes()).decode("ascii")


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


@dataclass
class _Prepared:
    lines: list[Polyline]
    staged: list[tuple[Polyline, TripClock, Checkpoints]]
    corridor: Corridor
    checkpoint_cells: list[list[str]]
    checkpoint_latlon: list[list[tuple[float, float]]]
    weather_cells: list[str]


def _prepare(cands: list[RouteCandidate], depart_s: float, req: s.TripRequest) -> _Prepared:
    lines: list[Polyline] = []
    staged: list[tuple[Polyline, TripClock, Checkpoints]] = []
    cp_cells: list[list[str]] = []
    cp_latlon: list[list[tuple[float, float]]] = []
    for c in cands:
        line = Polyline.from_coords(c.coords)
        profile = DriveProfile(line.cum_mi, c.cum_drive_s)
        if not c.truck_aware:
            profile = profile.capped(TRUCK_MAX_MPH)
        clock = TripClock.build(depart_s, profile, hos=DEFAULT_HOS if req.hos else None)
        cps = place_checkpoints(line.length_mi, req.interval_mi)
        lats, lons = line.points_at(cps.miles)
        cp_latlon.append([(float(a), float(b)) for a, b in zip(lats, lons, strict=True)])
        cp_cells.append(
            [h3.latlng_to_cell(float(a), float(b), CHECKPOINT_RES) for a, b in zip(lats, lons, strict=True)]
        )
        lines.append(line)
        staged.append((line, clock, cps))

    n_cp = len({c for cells in cp_cells for c in cells})
    corridor = build_corridor(lines, CORRIDOR_HALF_WIDTH_MI, sample_res=SAMPLE_RES)
    if n_cp + len(corridor.sample_cells) > WEATHER_POINT_BUDGET:
        corridor = build_corridor(lines, CORRIDOR_HALF_WIDTH_MI, sample_res=SAMPLE_RES - 1)
    weather_cells = sorted({c for cells in cp_cells for c in cells} | set(corridor.sample_cells))
    return _Prepared(lines, staged, corridor, cp_cells, cp_latlon, weather_cells)


def _segments(ev: RouteEvaluation) -> list[s.SegmentOut]:
    out: list[s.SegmentOut] = []
    cp = ev.plan.checkpoints
    for i, r in enumerate(ev.checkpoints):
        lvl = None if r.level is None else int(r.level)
        if out and out[-1].level == lvl:
            out[-1].to_mi = float(cp.end_mi[i])
        else:
            out.append(s.SegmentOut(from_mi=float(cp.start_mi[i]), to_mi=float(cp.end_mi[i]), level=lvl))
    return out


def _display_path(line: Polyline) -> tuple[list[tuple[float, float]], list[float]]:
    """Douglas-Peucker (~40 m) for the wire; keeps original vertices so miles stay exact."""
    simplified = shapely.simplify(LineString(np.column_stack([line.lons, line.lats])), 0.0004)
    kept = np.asarray(simplified.coords)
    path, path_mi, j = [], [], 0
    for lon, lat in kept:
        while j < len(line.lats) - 1 and not (line.lons[j] == lon and line.lats[j] == lat):
            j += 1
        path.append((round(float(lon), 5), round(float(lat), 5)))
        path_mi.append(round(float(line.cum_mi[j]), 3))
    return path, path_mi


def _fmt_hours(sec: float) -> str:
    h, m = divmod(round(sec / 60), 60)
    return f"{h} h {m:02d} min"


def _recommendation(ranking: Ranking, best_offset_h: int) -> s.RecommendationOut:
    best = ranking.recommended
    rid = best.route_id
    if ranking.advice is Advice.DELAY:
        headline = f"Every route crosses No Travel conditions. Route {rid} is the least exposed."
    elif ranking.advice is Advice.CAUTION:
        headline = f"Take Route {rid} with caution: {best.severe_mi:.0f} Severe miles is the lowest available."
    else:
        headline = f"Take Route {rid}: no Severe or No Travel miles."
    reasons = []
    for d in ranking.decisions:
        if d.criterion is None:
            reasons.append(f"Route {d.loser} is equivalent on every criterion; kept provider order.")
            continue
        c = next(c for c in CRITERIA if c.key == d.criterion)
        assert d.winner_value is not None and d.loser_value is not None
        if c.key == "duration_s":
            fmt_w, fmt_l = _fmt_hours(d.winner_value), _fmt_hours(d.loser_value)
        elif c.key == "avg_risk":
            fmt_w, fmt_l = f"{d.winner_value:.2f}", f"{d.loser_value:.2f}"
        else:
            fmt_w, fmt_l = f"{d.winner_value:.0f} mi", f"{d.loser_value:.0f} mi"
        reasons.append(f"Beats Route {d.loser} on {c.label}: {fmt_w} vs {fmt_l}.")
    if best_offset_h > 0:
        reasons.append(f"Leaving {best_offset_h} h later scores better — see departure advisor.")
    return s.RecommendationOut(route_id=rid, advice=ranking.advice, headline=headline, reasons=reasons)


def _heatmap(
    corridor: Corridor, grid: WeatherGrid, row_of: dict[str, int], load_lb: float, now_s: float
) -> s.HeatmapOut:
    start = int(now_s // HOUR * HOUR)
    i0 = int(np.clip(np.searchsorted(grid.times, start), 0, len(grid.times) - HEATMAP_HOURS))
    hrs = slice(i0, i0 + HEATMAP_HOURS)
    rows = np.array([row_of[c] for c in corridor.sample_cells])
    wind, rain, snow = (a[rows, hrs] for a in (grid.wind_mph, grid.rain_in_hr, grid.snow_in_hr))

    levels = levels_array(corridor.smooth(wind), corridor.smooth(rain), corridor.smooth(snow), load_lb)
    risk = np.where(levels < 0, 255, levels.astype(np.int16)).astype(np.uint8)
    nearest = corridor.idw_index[np.arange(len(corridor.cells)), np.argmax(corridor.idw_weight, axis=1)]

    def q(a: np.ndarray, scale: float) -> np.ndarray:
        return np.where(np.isnan(a), 255, np.clip(np.round(a * scale), 0, 254)).astype(np.uint8)

    return s.HeatmapOut(
        cells=corridor.cells,
        start=int(grid.times[i0]),
        hours=HEATMAP_HOURS,
        risk=_b64(risk),
        samples=len(corridor.sample_cells),
        sample_of=[int(i) for i in nearest],
        sample_wind=_b64(q(wind, 1)),
        sample_rain=_b64(q(rain, 100)),
        sample_snow=_b64(q(snow, 10)),
    )


def _compute(
    req: s.TripRequest, cands: list[RouteCandidate], prep: _Prepared, grid: WeatherGrid, depart_s: float
) -> tuple[list[s.RouteOut], s.RecommendationOut, s.DepartureAdviceOut, s.HeatmapOut]:
    row_of = {c: i for i, c in enumerate(prep.weather_cells)}
    plans = []
    for k, ((line, clock, cps), cells) in enumerate(zip(prep.staged, prep.checkpoint_cells, strict=True)):
        idx = np.array([row_of[c] for c in cells], dtype=np.intp)
        plans.append(RoutePlan(ROUTE_LABELS[k], line, clock, cps, idx))

    evals = [evaluate(p, grid, req.load_lb, req.wind_basis) for p in plans]
    ranking = rank([e.score for e in evals])
    advice = sweep_departures(plans, grid, req.load_lb, ADVISOR_HOURS, req.wind_basis)
    position = {sc.route_id: i for i, sc in enumerate(ranking.order)}
    lost = {d.loser: d for d in ranking.decisions}
    winner = ranking.recommended

    routes = []
    for ev, cand in zip(evals, cands, strict=True):
        p, sc = ev.plan, ev.score
        path, path_mi = _display_path(p.line)
        stop_mi = p.clock.stop_miles()
        slat, slon = p.line.points_at(stop_mi)
        stops = []
        for st, mi, a, b in zip(p.clock.stops, stop_mi, slat, slon, strict=True):
            arrive = p.clock.departure_s + float(p.clock.elapsed_s_at_drive(np.array([st.drive_s]))[0])
            stops.append(
                s.StopOut(
                    mile=round(float(mi), 2),
                    lat=float(a),
                    lon=float(b),
                    kind=st.kind.value,
                    arrive=int(arrive),
                    depart=int(arrive + st.duration_s),
                    tz=tz_at(float(a), float(b)),
                )
            )
        cp_out = []
        for r in ev.checkpoints:
            c, a = r.conditions, r.assessment
            cp_out.append(
                s.CheckpointOut(
                    mile=round(r.mile, 2),
                    lat=round(r.lat, 5),
                    lon=round(r.lon, 5),
                    eta=int(r.eta_s),
                    tz=tz_at(r.lat, r.lon),
                    wind_mph=None if c is None else round(c.wind_mph, 1),
                    gust_mph=None if c is None or c.gust_mph is None else round(c.gust_mph, 1),
                    rain_in_hr=None if c is None else round(c.rain_in_hr, 3),
                    snow_in_hr=None if c is None else round(c.snow_in_hr, 3),
                    crosswind_mph=None if r.crosswind_mph is None else round(r.crosswind_mph, 1),
                    level=None if a is None else int(a.level),
                    drivers=[] if a is None else [f.value for f in a.drivers],
                    reason="Beyond forecast horizon" if a is None else a.reason,
                    load_escalated=False if a is None else a.load_escalated,
                    confidence=r.confidence,
                )
            )
        d = lost.get(sc.route_id)
        lost_on = None
        if d is not None:
            label = next((c.label for c in CRITERIA if c.key == d.criterion), "tie")
            lost_on = s.DecisionOut(
                criterion=d.criterion, label=label, this_value=d.loser_value, winner_value=d.winner_value
            )
        routes.append(
            s.RouteOut(
                id=p.route_id,
                rank=position[sc.route_id] + 1,
                recommended=sc.route_id == winner.route_id,
                provider=cand.provider,
                truck_aware=cand.truck_aware,
                distance_mi=round(p.line.length_mi, 1),
                drive_s=round(p.clock.profile.total_drive_s),
                duration_s=round(sc.duration_s),
                arrival=int(depart_s + sc.duration_s),
                path=path,
                path_mi=path_mi,
                stops=stops,
                checkpoints=cp_out,
                segments=_segments(ev),
                score=s.ScoreOut(
                    miles_by_level=[round(m, 2) for m in sc.miles_by_level],
                    unknown_mi=round(sc.unknown_mi, 2),
                    no_travel_mi=round(sc.no_travel_mi, 2),
                    severe_mi=round(sc.severe_mi, 2),
                    high_mi=round(sc.high_mi, 2),
                    avg_risk=round(sc.avg_risk, 4),
                ),
                lost_on=lost_on,
            )
        )

    dep = s.DepartureAdviceOut(
        best_offset_h=advice.best_offset_h,
        options=[
            s.DepartureOptionOut(
                offset_h=o.offset_h,
                departure=int(depart_s + o.offset_h * HOUR),
                route_id=o.best.route_id,
                advice=o.advice,
                no_travel_mi=round(o.best.no_travel_mi, 1),
                severe_mi=round(o.best.severe_mi, 1),
                high_mi=round(o.best.high_mi, 1),
                avg_risk=round(o.best.avg_risk, 3),
                duration_s=round(o.best.duration_s),
                unknown_mi=round(o.best.unknown_mi, 1),
            )
            for o in advice.options
        ],
    )
    rec = _recommendation(ranking, advice.best_offset_h)
    heat = _heatmap(prep.corridor, grid, row_of, req.load_lb, time.time())
    return routes, rec, dep, heat


async def _warnings(
    routes: list[s.RouteOut],
    lookup: asyncio.Task[list[PointInfo | None]],
    sampled: list[list[int]],
    simulated: list[Alert] | None,
) -> tuple[list[s.WarningOut], Literal["ok", "unavailable"]]:
    """Name the places along each route and find official warnings. Never fails the trip."""
    try:
        infos: list[PointInfo | None] | None = await lookup
    except httpx.HTTPError as e:
        log.warning("nws points lookup failed: %s", type(e).__name__)
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
    except (TimeoutError, UpstreamError, httpx.HTTPError) as e:
        log.warning("warnings unavailable: %s", type(e).__name__)
        return [], "unavailable"


async def plan_trip(req: s.TripRequest) -> s.TripOut:
    t0 = time.perf_counter()
    origin_tz = tz_at(req.origin.lat, req.origin.lon)
    depart = req.departure_local.replace(tzinfo=ZoneInfo(origin_tz))
    depart_s = depart.timestamp()
    now = time.time()
    if depart_s < now - HOUR:
        raise TripError("Departure is in the past.")
    if depart_s > now + MAX_LEAD_DAYS * 24 * HOUR:
        raise TripError(f"Departure must be within {MAX_LEAD_DAYS} days: forecasts beyond that aren't decision-grade.")

    o, d = LatLon(req.origin.lat, req.origin.lon), LatLon(req.destination.lat, req.destination.lon)
    cands = await _routes(o, d, depart, req.load_lb)
    if not cands:
        raise TripError("No truck route found between these places.")
    t_route = time.perf_counter()

    prep = await asyncio.to_thread(_prepare, cands, depart_s, req)
    # Zone and town lookups run while the forecast downloads.
    sampled = [sample_indices(len(ll), req.interval_mi) for ll in prep.checkpoint_latlon]
    lookup = asyncio.create_task(
        nws.points([ll[i] for ll, idx in zip(prep.checkpoint_latlon, sampled, strict=True) for i in idx], POINTS_WAIT_S)
    )
    demo = DemoStormWeather() if req.weather == "demo_storm" else None
    weather = demo or get_weather_provider()
    grid = await weather.grid(prep.weather_cells)
    t_wx = time.perf_counter()

    routes, rec, dep, heat = await asyncio.to_thread(_compute, req, cands, prep, grid, depart_s)
    warnings, warnings_status = await _warnings(routes, lookup, sampled, demo_alerts(demo.anchor_s) if demo else None)
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
        recommendation=rec,
        departure_advice=dep,
        heatmap=heat,
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
