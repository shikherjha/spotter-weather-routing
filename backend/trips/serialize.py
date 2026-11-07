"""Engine results → API response objects (trips/schemas.py)."""

from __future__ import annotations

import base64

import numpy as np
import shapely
from shapely.geometry import LineString

from engine.advisor import DepartureAdvice
from engine.corridor import RENDER_RES, Corridor
from engine.evaluate import RouteEvaluation
from engine.geometry import Polyline
from engine.rules import WindBasis, levels_array
from engine.scoring import CRITERIA, Advice, Decision, Ranking
from engine.units import HOUR, FloatArray
from engine.weather import WeatherGrid
from providers.routing import RouteCandidate
from trips import schemas as s
from trips.limits import HEATMAP_HOURS
from trips.timezones import tz_at

DISPLAY_TOLERANCE_DEG = 0.0004  # ~40 m: path simplification for the wire
NO_DATA = 255


def _b64(arr: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(arr, dtype=np.uint8).tobytes()).decode("ascii")


def _segments(ev: RouteEvaluation) -> list[s.SegmentOut]:
    """Runs of consecutive checkpoints at the same level, as mile ranges."""
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
    """Douglas-Peucker simplified path; it keeps original vertices, so their miles stay exact."""
    simplified = shapely.simplify(LineString(np.column_stack([line.lons, line.lats])), DISPLAY_TOLERANCE_DEG)
    path, path_mi, j = [], [], 0
    for lon, lat in np.asarray(simplified.coords):
        while j < len(line.lats) - 1 and not (line.lons[j] == lon and line.lats[j] == lat):
            j += 1
        path.append((round(float(lon), 5), round(float(lat), 5)))
        path_mi.append(round(float(line.cum_mi[j]), 3))
    return path, path_mi


def _stops(ev: RouteEvaluation) -> list[s.StopOut]:
    clock, line = ev.plan.clock, ev.plan.line
    miles = clock.stop_miles()
    lats, lons = line.points_at(miles)
    out = []
    for st, mi, lat, lon in zip(clock.stops, miles, lats, lons, strict=True):
        arrive = clock.departure_s + float(clock.elapsed_s_at_drive(np.array([st.drive_s]))[0])
        out.append(
            s.StopOut(
                mile=round(float(mi), 2),
                lat=float(lat),
                lon=float(lon),
                kind=st.kind.value,
                arrive=int(arrive),
                depart=int(arrive + st.duration_s),
                tz=tz_at(float(lat), float(lon)),
            )
        )
    return out


def _checkpoints(ev: RouteEvaluation) -> list[s.CheckpointOut]:
    out = []
    for r in ev.checkpoints:
        c, a = r.conditions, r.assessment
        out.append(
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
    return out


def _lost_on(d: Decision | None) -> s.DecisionOut | None:
    if d is None:
        return None
    label = next((c.label for c in CRITERIA if c.key == d.criterion), "tie")
    return s.DecisionOut(criterion=d.criterion, label=label, this_value=d.loser_value, winner_value=d.winner_value)


def routes_out(
    evals: list[RouteEvaluation], cands: list[RouteCandidate], ranking: Ranking, depart_s: float
) -> list[s.RouteOut]:
    position = {sc.route_id: i for i, sc in enumerate(ranking.order)}
    lost = {d.loser: d for d in ranking.decisions}
    out = []
    for ev, cand in zip(evals, cands, strict=True):
        p, sc = ev.plan, ev.score
        path, path_mi = _display_path(p.line)
        out.append(
            s.RouteOut(
                id=p.route_id,
                rank=position[sc.route_id] + 1,
                recommended=sc.route_id == ranking.recommended.route_id,
                provider=cand.provider,
                truck_aware=cand.truck_aware,
                distance_mi=round(p.line.length_mi, 1),
                drive_s=round(p.clock.profile.total_drive_s),
                duration_s=round(sc.duration_s),
                arrival=int(depart_s + sc.duration_s),
                path=path,
                path_mi=path_mi,
                stops=_stops(ev),
                checkpoints=_checkpoints(ev),
                segments=_segments(ev),
                score=s.ScoreOut(
                    miles_by_level=[round(m, 2) for m in sc.miles_by_level],
                    unknown_mi=round(sc.unknown_mi, 2),
                    no_travel_mi=round(sc.no_travel_mi, 2),
                    severe_mi=round(sc.severe_mi, 2),
                    high_mi=round(sc.high_mi, 2),
                    avg_risk=round(sc.avg_risk, 4),
                ),
                lost_on=_lost_on(lost.get(sc.route_id)),
            )
        )
    return out


def _fmt_hours(sec: float) -> str:
    h, m = divmod(round(sec / 60), 60)
    return f"{h} h {m:02d} min"


def recommendation_out(ranking: Ranking, best_offset_h: int) -> s.RecommendationOut:
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
        if d.criterion is None or d.winner_value is None or d.loser_value is None:
            reasons.append(f"Route {d.loser} is equivalent on every criterion; kept provider order.")
            continue
        label = next(c.label for c in CRITERIA if c.key == d.criterion)
        if d.criterion == "duration_s":
            won, lost = _fmt_hours(d.winner_value), _fmt_hours(d.loser_value)
        elif d.criterion == "avg_risk":
            won, lost = f"{d.winner_value:.2f}", f"{d.loser_value:.2f}"
        else:
            won, lost = f"{d.winner_value:.0f} mi", f"{d.loser_value:.0f} mi"
        reasons.append(f"Beats Route {d.loser} on {label}: {won} vs {lost}.")
    if best_offset_h > 0:
        reasons.append(f"Leaving {best_offset_h} h later scores better — see departure advisor.")
    return s.RecommendationOut(route_id=rid, advice=ranking.advice, headline=headline, reasons=reasons)


def departure_advice_out(advice: DepartureAdvice, depart_s: float) -> s.DepartureAdviceOut:
    return s.DepartureAdviceOut(
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


def _wind(grid: WeatherGrid, basis: WindBasis) -> FloatArray:
    """The wind the checkpoints were judged on, so map and route colours agree."""
    gust = np.where(np.isnan(grid.gust_mph), grid.wind_mph, grid.gust_mph)
    if basis is WindBasis.GUST:
        return gust
    if basis is WindBasis.WORST:
        return np.fmax(grid.wind_mph, gust)
    return grid.wind_mph


def heatmap_out(
    corridor: Corridor, grid: WeatherGrid, row_of: dict[str, int], load_lb: float, basis: WindBasis, start_s: float
) -> s.HeatmapOut:
    """Risk per corridor cell per hour for HEATMAP_HOURS from `start_s`, packed as base64 bytes."""
    i0 = int(np.clip(np.searchsorted(grid.times, start_s // HOUR * HOUR), 0, len(grid.times) - HEATMAP_HOURS))
    hours = slice(i0, i0 + HEATMAP_HOURS)
    rows = np.array([row_of[c] for c in corridor.sample_cells])
    wind, rain, snow = (a[rows, hours] for a in (_wind(grid, basis), grid.rain_in_hr, grid.snow_in_hr))
    levels = levels_array(corridor.smooth(wind), corridor.smooth(rain), corridor.smooth(snow), load_lb)
    risk = np.where(levels < 0, NO_DATA, levels.astype(np.int16)).astype(np.uint8)
    return s.HeatmapOut(
        cells=corridor.cells,
        start=int(grid.times[i0]),
        hours=HEATMAP_HOURS,
        risk=_b64(risk),
        resolution=RENDER_RES,
    )
